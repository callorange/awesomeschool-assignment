import json
from io import StringIO
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4, uuid7

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from education.management.commands import seed_educations
from education.models import Education


class PresetTests(TestCase):
    """실제 DB와 임시 미디어로 초기화의 보존·롤백·재실행 계약을 검증한다.

    저장소 실패만 주입하며 DB transaction 자체는 mock으로 대체하지 않는다.
    """

    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.media = self.root / "media"
        self.enterContext(override_settings(MEDIA_ROOT=self.media))

    def seed(self):
        output = StringIO()
        call_command("seed_educations", stdout=output)
        return output.getvalue()

    def files(self):
        """파일명과 내용의 보존을 함께 비교할 수 있는 스냅샷을 반환한다."""
        return {
            str(p.relative_to(self.media)): p.read_bytes()
            for p in self.media.rglob("*")
            if p.is_file()
        }

    def test_seed_and_rerun_preserve_data_and_images(self):
        self.assertIn("생성 3개", self.seed())
        self.assertEqual(Education.objects.count(), 3)
        for education in Education.objects.all():
            self.assertRegex(
                education.image.name,
                rf"^education/{education.media_id.hex}/images/[0-9a-f]{{64}}\.png$",
            )
            self.assertEqual(education.operation_type, "instructor_led")
            self.assertEqual(
                education.operation_note,
                "교육 일정과 진행 조건은 상담 후 협의하여 확정합니다.",
            )
            self.assertIs(education.is_accepting_inquiries, True)
        original = self.files()
        self.assertEqual(len(original), 3)
        education = Education.objects.get(slug="prompt-hero")
        education.summary = "사용자가 수정한 소개"
        education.operation_type = Education.OperationType.COURSEWARE
        education.operation_note = "사용자가 수정한 운영 안내"
        education.is_accepting_inquiries = False
        education.save(
            update_fields=[
                "summary",
                "operation_type",
                "operation_note",
                "is_accepting_inquiries",
            ]
        )
        # 같은 이미지를 참조하는 별도 교육도 재실행으로 훼손되지 않아야 한다.
        education.pk = None
        education.media_id = uuid7()
        education.slug = "other-education"
        education.save()
        self.assertIn("생성 0개, 건너뜀 3개", self.seed())
        self.assertEqual(Education.objects.count(), 4)
        self.assertEqual(
            Education.objects.get(slug="prompt-hero").summary, "사용자가 수정한 소개"
        )
        self.assertEqual(self.files(), original)
        education = Education.objects.get(slug="prompt-hero")
        self.assertEqual(education.operation_type, "courseware")
        self.assertEqual(education.operation_note, "사용자가 수정한 운영 안내")
        self.assertIs(education.is_accepting_inquiries, False)

    def test_partial_database_reuses_existing_image(self):
        self.seed()
        original = self.files()
        Education.objects.filter(slug="emotion-hero").delete()
        self.assertIn("생성 1개, 건너뜀 2개", self.seed())
        self.assertEqual(Education.objects.count(), 3)
        self.assertEqual(self.files(), original)

    def test_legacy_image_reference_is_preserved(self):
        storage = FileSystemStorage(location=self.media, base_url="/media/")
        key = storage.save("education/presets/legacy.png", ContentFile(b"legacy"))
        Education.objects.create(slug="prompt-hero", image=key)
        self.assertIn("생성 2개, 건너뜀 1개", self.seed())
        education = Education.objects.get(slug="prompt-hero")
        self.assertEqual(education.image.name, key)
        self.assertEqual((self.media / key).read_bytes(), b"legacy")
        self.assertEqual(len(self.files()), 3)

    def test_invalid_input_or_missing_image_has_no_side_effects(self):
        destination = self.root / "data"
        copytree(seed_educations.PRESET_PATH.parent, destination)
        source = destination / "education_presets.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        for change in (
            "missing-image",
            "empty-goals",
            "period-order",
            "unknown-operation",
            "missing-description",
            "missing-media-id",
            "invalid-media-id",
            "duplicate-media-id",
            "wrong-uuid-version",
        ):
            modified = json.loads(json.dumps(records))
            if change == "missing-image":
                modified[-1]["image"] = "images/missing.png"
            elif change == "empty-goals":
                modified[-1]["goals"] = []
            elif change == "unknown-operation":
                modified[-1]["operation_type"] = "unknown"
            elif change == "missing-description":
                del modified[-1]["curriculum"][0]["lessons"][0]["description"]
            elif change == "missing-media-id":
                del modified[-1]["media_id"]
            elif change == "invalid-media-id":
                modified[-1]["media_id"] = "../invalid"
            elif change == "duplicate-media-id":
                modified[-1]["media_id"] = modified[0]["media_id"]
            elif change == "wrong-uuid-version":
                modified[-1]["media_id"] = str(uuid4())
            else:
                modified[-1]["curriculum"][0]["lessons"][0]["period"] = 9
            source.write_text(json.dumps(modified), encoding="utf-8")
            with (
                self.subTest(change=change),
                patch.object(seed_educations, "PRESET_PATH", source),
                self.assertRaises(CommandError),
            ):
                self.seed()
            self.assertFalse(Education.objects.exists())
            self.assertEqual(self.files(), {})

    def test_storage_failure_rolls_back_database_and_retry_reuses_file(self):
        storage = FileSystemStorage(location=self.media, base_url="/media/")
        save = storage.save
        count = 0

        def fail_second_save(name, content):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("저장소 쓰기 실패")
            return save(name, content)

        errors = StringIO()
        with (
            patch.object(seed_educations, "default_storage", storage),
            patch.object(storage, "save", side_effect=fail_second_save),
            self.assertRaises(CommandError),
        ):
            call_command("seed_educations", stderr=errors, stdout=StringIO())
        self.assertFalse(Education.objects.exists())
        self.assertEqual(len(self.files()), 1)
        self.assertIn("파일 1개가 남을 수", errors.getvalue())
        remaining = self.files()
        self.assertIn("생성 3개", self.seed())
        self.assertEqual(len(self.files()), 3)
        for name, data in remaining.items():
            self.assertEqual(self.files()[name], data)

    def test_storage_returned_filename_is_persisted(self):
        storage = FileSystemStorage(location=self.media, base_url="/media/")
        save = storage.save

        def renamed(name, content):
            return save(name.replace(".png", "-stored.png"), content)

        with (
            patch.object(seed_educations, "default_storage", storage),
            patch.object(storage, "save", side_effect=renamed),
        ):
            self.seed()
        for education in Education.objects.all():
            self.assertTrue(education.image.name.endswith("-stored.png"))
            self.assertTrue(storage.exists(education.image.name))
