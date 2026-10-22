"""임시 저장소와 실제 ORM으로 교육 이미지 경로·수명주기를 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from multiprocessing import Value
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django_q.brokers import get_broker
from django_q.models import Failure, OrmQ
from django_q.monitor import monitor
from django_q.signing import SignedPackage
from django_q.tasks import async_task
from django_q.worker import worker

from education.media import education_image_upload_to
from education.models import Education


class EducationImagePathTests(TestCase):
    """파일명·내용 보존을 검사하며 commit 후 정리는 별도 transaction 테스트로 검증한다.

    TestCase에서는 큐를 실행하지 않아 교체 전후 파일을 비교할 수 있다.
    """

    def setUp(self):
        self.media = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.media))

    def test_same_source_name_uses_distinct_uuid_keys_without_overwrite(self):
        education = Education.objects.create(slug="image-path")
        education.image.save("original.PNG", ContentFile(b"first"))
        first = education.image.name
        education.image.save("original.PNG", ContentFile(b"second"))
        second = education.image.name
        self.assertNotEqual(first, second)
        for key in (first, second):
            self.assertRegex(
                key, rf"^education/{education.media_id.hex}/images/[0-9a-f]{{32}}\.png$"
            )
        self.assertEqual((self.media / first).read_bytes(), b"first")
        self.assertEqual((self.media / second).read_bytes(), b"second")
        education.refresh_from_db()
        self.assertEqual(education.image.name, second)
        self.assertEqual(education.image.url, "/media/" + second)

    def test_unsaved_education_has_uuid7_path_without_database_access(self):
        with self.assertNumQueries(0):
            education = Education(slug="unsaved")
            key = education_image_upload_to(education, "original.PNG")
        self.assertIsNone(education.pk)
        self.assertEqual(education.media_id.version, 7)
        self.assertRegex(
            key, rf"^education/{education.media_id.hex}/images/[0-9a-f]{{32}}\.png$"
        )

    def test_slug_change_and_replacement_keep_uuid_directory(self):
        education = Education.objects.create(slug="before")
        education.image.save("first.png", ContentFile(b"first"))
        original_id = education.media_id
        original_directory = education.image.name.rsplit("/", 1)[0]
        education.slug = "after"
        education.save(update_fields=["slug"])
        education.refresh_from_db()
        education.image.save("second.png", ContentFile(b"second"))
        education.refresh_from_db()
        self.assertEqual(education.media_id, original_id)
        self.assertEqual(education.image.name.rsplit("/", 1)[0], original_directory)

    def test_storage_renamed_key_is_persisted(self):
        education = Education.objects.create(slug="collision")
        with patch("education.media.uuid4") as uuid:
            uuid.return_value.hex = "a" * 32
            education.image.save("same.png", ContentFile(b"first"))
            first = education.image.name
            education.image.save("same.png", ContentFile(b"second"))
        education.refresh_from_db()
        self.assertNotEqual(education.image.name, first)
        self.assertEqual((self.media / first).read_bytes(), b"first")
        self.assertEqual((self.media / education.image.name).read_bytes(), b"second")

    def test_legacy_key_and_slug_change_do_not_move_file(self):
        storage = Education._meta.get_field("image").storage
        key = storage.save("education/presets/legacy.png", ContentFile(b"legacy"))
        education = Education.objects.create(slug="old-slug", image=key)
        education.slug = "new-slug"
        education.save()
        education.refresh_from_db()
        self.assertEqual(education.image.name, key)
        self.assertEqual(education.image.url, "/media/" + key)
        self.assertEqual((self.media / key).read_bytes(), b"legacy")
        self.assertEqual(len(list(self.media.rglob("*.png"))), 1)


class EducationImageLifecycleTests(TransactionTestCase):
    """실제 commit·rollback과 임시 Storage로 파일 삭제의 영향을 검증한다."""

    def setUp(self):
        self.media = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.media))
        self.storage = Education._meta.get_field("image").storage

    def education(self, slug, key=None):
        """기존 키를 공유하거나 임시 파일을 새로 저장한 교육을 테스트 DB에 만든다."""
        if key is None:
            key = self.storage.save(
                f"education/presets/{slug}.png", ContentFile(slug.encode())
            )
        return Education.objects.create(slug=slug, image=key)

    def run_cleanup(self):
        """격리된 ORM 큐의 payload를 실제 Q2 worker·monitor로 처리한다."""
        inputs, results = Queue(), Queue()
        for row in OrmQ.objects.order_by("pk"):
            task = SignedPackage.loads(row.payload)
            task["ack_id"] = row.pk
            inputs.put(task)
        inputs.put("STOP")
        worker(inputs, results, Value("f", -1), timeout=-1)
        results.put("STOP")
        monitor(results, get_broker())

    def test_single_and_bulk_delete_wait_for_commit(self):
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                education = self.education(f"delete-{bulk}")
                key = education.image.name
                with transaction.atomic():
                    if bulk:
                        Education.objects.filter(pk=education.pk).delete()
                    else:
                        education.delete()
                    self.assertTrue(self.storage.exists(key))
                self.assertTrue(self.storage.exists(key))
                self.assertTrue(OrmQ.objects.exists())
                self.run_cleanup()
                self.assertFalse(self.storage.exists(key))

    def test_delete_rollback_preserves_row_and_file(self):
        education = self.education("rollback")
        pk, key = education.pk, education.image.name
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                education.delete()
                raise RuntimeError("rollback")
        self.assertTrue(Education.objects.filter(pk=pk, image=key).exists())
        self.assertTrue(self.storage.exists(key))
        self.assertFalse(OrmQ.objects.exists())

    def test_shared_file_is_deleted_only_after_last_reference(self):
        first = self.education("shared")
        key = first.image.name
        second = self.education("second", key)
        first.delete()
        self.run_cleanup()
        self.assertTrue(self.storage.exists(key))
        self.assertEqual(second.image.name, key)
        second.delete()
        self.run_cleanup()
        self.assertFalse(self.storage.exists(key))

    def test_replacement_cleans_old_file_after_commit(self):
        education = self.education("replacement")
        old = education.image.name
        with transaction.atomic():
            education.image.save("new.png", ContentFile(b"new"))
            self.assertTrue(self.storage.exists(old))
            new = education.image.name
        self.assertTrue(self.storage.exists(old))
        self.run_cleanup()
        self.assertFalse(self.storage.exists(old))
        self.assertEqual((self.media / new).read_bytes(), b"new")
        education.refresh_from_db()
        self.assertEqual(education.image.name, new)

    def test_replacement_rollback_preserves_old_file(self):
        education = self.education("replace-rollback")
        old = education.image.name
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                education.image.save("new.png", ContentFile(b"new"))
                new = education.image.name
                raise RuntimeError("rollback")
        education.refresh_from_db()
        self.assertEqual(education.image.name, old)
        self.assertTrue(self.storage.exists(old))
        # DB에 연결되기 전에 저장된 새 파일은 rollback으로 지워지지 않는다.
        self.assertTrue(self.storage.exists(new))
        self.assertFalse(OrmQ.objects.exists())

    def test_shared_file_is_preserved_during_replacement(self):
        education = self.education("shared-replace")
        old = education.image.name
        other = self.education("other", old)
        education.image.save("new.png", ContentFile(b"new"))
        self.run_cleanup()
        self.assertTrue(self.storage.exists(old))
        self.assertEqual(
            (self.media / other.image.name).read_bytes(), b"shared-replace"
        )
        self.assertTrue(self.storage.exists(education.image.name))

    def test_unrelated_and_excluded_image_updates_do_not_delete_files(self):
        education = self.education("unchanged")
        original = education.image.name
        with patch.object(self.storage, "delete") as delete:
            education.summary = "새 소개"
            education.save()
            education.operation_note = "새 안내"
            education.save(update_fields=["operation_note"])
            education.image = "education/not-saved.png"
            education.save(update_fields=["summary"])
            delete.assert_not_called()
        education.refresh_from_db()
        self.assertFalse(OrmQ.objects.exists())
        self.assertEqual(education.image.name, original)
        self.assertTrue(self.storage.exists(original))

    def test_reconnected_key_is_preserved_at_commit(self):
        education = self.education("reconnect")
        old = education.image.name
        with transaction.atomic():
            education.image.save("new.png", ContentFile(b"new"))
            new = education.image.name
            education.image = old
            education.save(update_fields=["image"])
        self.run_cleanup()
        self.assertTrue(self.storage.exists(old))
        self.assertFalse(self.storage.exists(new))

    def test_deleted_key_reconnected_before_commit_is_preserved(self):
        education = self.education("delete-reconnect")
        key = education.image.name
        with transaction.atomic():
            education.delete()
            self.education("new-owner", key)
        self.run_cleanup()
        self.assertTrue(self.storage.exists(key))

    def test_seed_recreates_file_after_committed_deletion(self):
        call_command("seed_educations", stdout=StringIO())
        education = Education.objects.get(slug="emotion-hero")
        key = education.image.name
        original = (self.media / key).read_bytes()
        education.delete()
        self.run_cleanup()
        self.assertFalse(self.storage.exists(key))
        call_command("seed_educations", stdout=StringIO())
        self.assertEqual(Education.objects.count(), 3)
        self.assertEqual(Education.objects.get(slug="emotion-hero").image.name, key)
        self.assertEqual((self.media / key).read_bytes(), original)
        source = settings.BASE_DIR.parent / "presets/education/images/emotion.png"
        self.assertEqual(source.read_bytes(), original)

    def test_replacement_delete_failure_keeps_committed_new_reference(self):
        education = self.education("replacement-failure")
        old = education.image.name
        with (
            patch.object(self.storage, "delete", side_effect=OSError("storage error")),
            self.assertLogs("django-q", level="ERROR") as logs,
        ):
            education.image.save("new.png", ContentFile(b"new"))
            for _ in range(3):
                self.run_cleanup()
        new = education.image.name
        education.refresh_from_db()
        self.assertEqual(education.image.name, new)
        self.assertTrue(self.storage.exists(old))
        self.assertEqual((self.media / new).read_bytes(), b"new")
        self.assertIn(old, " ".join(logs.output))
        self.assertEqual(Failure.objects.get().attempt_count, 3)
        self.assertFalse(OrmQ.objects.exists())
        self.education("reused-failure", old)
        async_task(
            "education.tasks.delete_unreferenced_education_image",
            old,
            "default",
            "default",
            ack_failure=False,
        )
        self.run_cleanup()
        self.assertTrue(self.storage.exists(old))

    def test_delete_failure_is_logged_without_blocking_other_callbacks(self):
        first = self.education("failure")
        second = self.education("success")
        first_pk = first.pk
        first_key, second_key = first.image.name, second.image.name
        unrelated = self.storage.save("unrelated.png", ContentFile(b"keep"))
        delete = self.storage.delete

        def fail_first(name):
            if name == first_key:
                raise OSError("sensitive-detail-must-not-be-logged")
            delete(name)

        with (
            patch.object(self.storage, "delete", side_effect=fail_first),
            self.assertLogs("django-q", level="ERROR") as logs,
        ):
            with transaction.atomic():
                first.delete()
                second.delete()
            self.run_cleanup()
        self.assertFalse(Education.objects.filter(pk=first_pk).exists())
        self.assertTrue(self.storage.exists(first_key))
        self.assertFalse(self.storage.exists(second_key))
        self.assertTrue(self.storage.exists(unrelated))
        self.assertIn(first_key, " ".join(logs.output))
        self.assertIn("OSError", " ".join(logs.output))
        self.assertNotIn("sensitive-detail", " ".join(logs.output))

    def test_uncommitted_queue_is_not_visible_in_another_connection(self):
        education = self.education("visibility")

        def visible_count():
            close_old_connections()
            try:
                return OrmQ.objects.count()
            finally:
                close_old_connections()

        with transaction.atomic():
            education.delete()
            self.assertEqual(OrmQ.objects.count(), 1)
            with ThreadPoolExecutor(max_workers=1) as executor:
                self.assertEqual(executor.submit(visible_count).result(timeout=5), 0)
        self.assertEqual(OrmQ.objects.count(), 1)

    def test_enqueue_failure_rolls_back_save_and_delete(self):
        education = self.education("enqueue-failure")
        original = education.image.name
        with patch(
            "education.signals.async_task",
            side_effect=RuntimeError("queue unavailable"),
        ):
            education.image = "education/new-key.png"
            with self.assertRaises(RuntimeError):
                education.save(update_fields=["image"])
            education.refresh_from_db()
            self.assertEqual(education.image.name, original)
            with self.assertRaises(RuntimeError):
                education.delete()
        self.assertTrue(Education.objects.filter(image=original).exists())
        self.assertFalse(OrmQ.objects.exists())

    def test_missing_file_and_repeated_cleanup_are_successful(self):
        for _ in range(2):
            async_task(
                "education.tasks.delete_unreferenced_education_image",
                "education/missing.png",
                "default",
                "default",
                ack_failure=False,
            )
        self.run_cleanup()
        self.assertFalse(OrmQ.objects.exists())
        self.assertFalse(Failure.objects.exists())
