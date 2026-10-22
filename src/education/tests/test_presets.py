import json
from collections import Counter
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4, uuid7
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from django_q.models import OrmQ, Schedule

from education.management.commands import seed_educations
from education.models import (
    ConsultationRecord,
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
    MailAttempt,
    MailSendBudget,
)
from education.services.applications import save_application


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
            patch("education.signals.async_task") as queue,
        ):
            self.seed()
        queue.assert_not_called()
        self.assertFalse(OrmQ.objects.exists())
        for education in Education.objects.all():
            self.assertTrue(education.image.name.endswith("-stored.png"))
            self.assertTrue(storage.exists(education.image.name))


@override_settings(SETTINGS_MODULE="config.settings.dev")
class ApplicationPresetTests(TestCase):
    """개발 샘플의 실제 저장·이력·재실행·외부 효과와 날짜 관계를 검증한다.

    PostgreSQL 테스트 DB·임시 미디어와 가상 staff를 사용하고 한국 자정 직후로
    시계를 고정한다. 실제 ORM 저장은 유지하며 외부 경계와 실패 지점만 대체한다.
    """

    def setUp(self):
        self.media = Path(self.enterContext(TemporaryDirectory()))
        # override_settings의 모듈 식별자 초기화가 실제 개발 환경 검사를 가리지 않게 한다.
        self.enterContext(
            override_settings(
                MEDIA_ROOT=self.media, SETTINGS_MODULE="config.settings.dev"
            )
        )
        self.author = get_user_model().objects.create_user(
            "preset-staff", is_staff=True
        )
        self.now = datetime(2026, 10, 23, 0, 1, tzinfo=ZoneInfo("Asia/Seoul"))
        self.enterContext(
            patch.object(seed_educations.timezone, "now", return_value=self.now)
        )

    def seed(self, **options):
        output = StringIO()
        call_command(
            "seed_educations",
            with_applications=True,
            staff_user=self.author.username,
            stdout=output,
            **options,
        )
        return output.getvalue()

    def snapshot(self):
        """현재값뿐 아니라 이력과 큐·계정까지 비교할 수 있는 DB 스냅샷이다."""
        return [
            list(model.objects.order_by("pk").values())
            for model in (
                Education,
                EducationApplication,
                EducationApplication.history.model,
                ConsultationRecord,
                EducationApplicationReminderEmail,
                MailAttempt,
                MailSendBudget,
                OrmQ,
                Schedule,
                get_user_model(),
            )
        ]

    def test_exact_distribution_dates_relations_and_no_external_effects(self):
        with (
            patch("django.core.mail.EmailMessage.send") as send,
            patch("education.signals.async_task") as queue,
            patch("education.tasks.reminder_dispatch.async_task") as dispatch,
        ):
            self.assertIn("신청 생성 32개, 건너뜀 0개", self.seed())
        send.assert_not_called()
        queue.assert_not_called()
        dispatch.assert_not_called()
        self.assertFalse(OrmQ.objects.exists())
        self.assertFalse(Schedule.objects.exists())
        self.assertFalse(MailSendBudget.objects.exists())
        applications = list(EducationApplication.objects.order_by("-created_at", "-pk"))
        self.assertEqual(len(applications), 32)
        self.assertEqual(
            Counter(item.education_slug for item in applications),
            {"prompt-hero": 11, "emotion-hero": 11, "relationship-hero": 10},
        )
        self.assertEqual(
            Counter(item.status for item in applications),
            {
                "received": 8,
                "consulting": 6,
                "follow_up": 10,
                "completed": 4,
                "cancelled": 4,
            },
        )
        states = Counter()
        dates = set()
        for application in applications:
            self.assertLessEqual(application.created_at, self.now)
            self.assertGreaterEqual(
                application.contact_date,
                timezone.localtime(application.created_at).date(),
            )
            dates.add(
                (application.contact_date > self.now.date())
                - (application.contact_date < self.now.date())
            )
            self.assertTrue(application.email.endswith("@example.com"))
            self.assertEqual(
                application.submission_snapshot["email"], application.email
            )
            history = application.history.get()
            self.assertIsNone(history.history_user_id)
            self.assertEqual(history.history_date, application.created_at)
            self.assertIn("샘플", history.history_change_reason)
            if application.status != "follow_up":
                self.assertIsNone(application.next_contact_at)
            if application.status == "cancelled":
                self.assertTrue(application.cancellation_reason)
            for record in application.consultations.all():
                self.assertEqual(record.author_id, self.author.pk)
                self.assertLessEqual(application.created_at, record.created_at)
                self.assertLessEqual(record.created_at, self.now)
                self.assertIn("[샘플]", record.content)
                if record.next_contact_at:
                    self.assertLessEqual(record.created_at, record.next_contact_at)
                if record.corrects_id:
                    self.assertEqual(record.corrects.application_id, application.pk)
                    self.assertLessEqual(record.corrects.created_at, record.created_at)
            row = application.notification
            states[row.state] += 1
            self.assert_notification(application)
        self.assertEqual(dates, {-1, 0, 1})
        self.assertEqual(
            states,
            {
                "pending": 8,
                "queued": 3,
                "sending": 2,
                "simulated": 7,
                "retry_wait": 3,
                "failed": 2,
                "unknown": 3,
                "suppressed": 4,
            },
        )
        follows = [item for item in applications if item.status == "follow_up"]
        self.assertEqual(
            Counter(
                "undated"
                if item.next_contact_at is None
                else "today"
                if timezone.localtime(item.next_contact_at).date() == self.now.date()
                else "past"
                if item.next_contact_at < self.now
                else "future"
                for item in follows
            ),
            {"today": 3, "past": 3, "future": 2, "undated": 2},
        )
        for page in (applications[:20], applications[20:]):
            self.assertEqual(len({item.status for item in page}), 5)
            self.assertEqual(len({item.education_slug for item in page}), 3)
        self.assertTrue(
            EducationApplication.objects.filter(consultations__isnull=True).exists()
        )
        self.assertTrue(ConsultationRecord.objects.filter(result="correction").exists())

    def assert_notification(self, application):
        """안내와 현재 시도의 실제 관계·처리 시각을 확인한다."""
        row = application.notification
        self.assertEqual(row.mode, "simulated")
        self.assertIsNone(row.sent_at)
        self.assertEqual(row.ses_message_id, "")
        self.assertEqual(row.attempt_count, row.attempts.count())
        self.assertEqual(
            row.due_at,
            max(
                application.created_at,
                datetime.combine(
                    application.contact_date,
                    datetime.min.time().replace(hour=9),
                    ZoneInfo("Asia/Seoul"),
                ),
            ),
        )
        if row.attempt_count:
            attempt = row.attempts.get(pk=row.attempt_id)
            self.assertEqual(attempt.started_at, row.started_at)
            self.assertEqual(attempt.state, row.state)
            self.assertLessEqual(row.due_at, attempt.started_at)
            self.assertLessEqual(attempt.started_at, self.now)
            if attempt.finished_at:
                self.assertLessEqual(attempt.started_at, attempt.finished_at)
                self.assertLessEqual(attempt.finished_at, self.now)
            if row.simulated_at:
                self.assertEqual(row.simulated_at, attempt.finished_at)
            if row.next_retry_at:
                self.assertGreaterEqual(row.next_retry_at, attempt.finished_at)
        else:
            self.assertIsNone(row.attempt_id)
            self.assertIsNone(row.started_at)

    def test_korean_date_boundary_uses_one_basis(self):
        educations = {
            fields["slug"]: Education(**fields)
            for fields, _ in seed_educations._load_presets()
        }
        for now in (self.now, self.now.replace(hour=23, minute=59)):
            with self.subTest(now=now):
                prepared = seed_educations._load_applications(
                    educations, self.author, now
                )
                for application, consultations, row, attempt in prepared:
                    self.assertLessEqual(application.created_at, now)
                    self.assertGreaterEqual(
                        application.contact_date, application.created_at.date()
                    )
                    for record, _ in consultations:
                        self.assertLessEqual(application.created_at, record.created_at)
                        self.assertLessEqual(record.created_at, now)
                today = [
                    a
                    for a, *_ in prepared
                    if a.next_contact_at and a.next_contact_at.date() == now.date()
                ]
                self.assertEqual(len(today), 3)

    def test_rerun_preserves_edits_children_history_and_other_data(self):
        self.seed()
        application = EducationApplication.objects.get(
            email="application-preset-01@example.com"
        )
        save_application(
            application.pk,
            {
                "name": "담당자 정정",
                "email": "edited@example.com",
                "address": "담당자 주소",
                "status": "consulting",
            },
            self.author,
        )
        ConsultationRecord.objects.create(
            application=application,
            author=self.author,
            result="consulted",
            content="추가 상담",
        )
        application.education = None
        application.save(update_fields=["education"])
        # 일반 신청은 샘플 생성과 재실행에서 모두 유지한다.
        from education.tests.test_notifications import notification

        notification()
        before = self.snapshot()
        files = {p.name: p.read_bytes() for p in self.media.rglob("*.png")}
        with patch.object(
            seed_educations.timezone, "now", return_value=self.now + timedelta(days=10)
        ):
            self.assertIn("신청 생성 0개, 건너뜀 32개", self.seed())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.media.rglob("*.png")}, files
        )

    def test_partial_seed_only_adds_missing_applications(self):
        save = seed_educations._save_applications
        # 일부만 있는 DB를 만들 때도 원래 저장·이력 생성 경로를 그대로 실행한다.
        with patch.object(
            seed_educations,
            "_save_applications",
            side_effect=lambda rows, educations: save(rows[:3], educations),
        ):
            self.seed()
        before = list(EducationApplication.objects.order_by("pk").values())
        self.assertIn("신청 생성 29개, 건너뜀 3개", self.seed())
        self.assertEqual(
            list(EducationApplication.objects.order_by("pk").values())[:3], before
        )
        self.assertEqual(EducationApplication.history.count(), 32)

    def test_invalid_options_environment_and_staff_do_not_write(self):
        inactive = get_user_model().objects.create_user(
            "inactive", is_staff=True, is_active=False
        )
        ordinary = get_user_model().objects.create_user("ordinary")
        for username in (None, "missing", inactive.username, ordinary.username):
            with self.subTest(username=username), self.assertRaises(CommandError):
                call_command(
                    "seed_educations", with_applications=True, staff_user=username
                )
        for settings in (
            {"SETTINGS_MODULE": "config.settings.prod"},
            {"NOTIFICATION_MODE": "ses"},
            {"MAILERS": {"default": {"BACKEND": "django_ses.SESBackend"}}},
        ):
            with (
                self.subTest(settings=settings),
                override_settings(
                    **{"SETTINGS_MODULE": "config.settings.dev", **settings}
                ),
                self.assertRaises(CommandError),
            ):
                self.seed()
        with self.assertRaises(CommandError):
            call_command("seed_educations", staff_user=self.author.username)
        self.assertFalse(Education.objects.exists())
        self.assertFalse(list(self.media.rglob("*.png")))

    def test_default_command_keeps_production_education_contract(self):
        with override_settings(
            SETTINGS_MODULE="config.settings.prod", NOTIFICATION_MODE="ses"
        ):
            call_command("seed_educations", stdout=StringIO())
        self.assertEqual(Education.objects.count(), 3)
        self.assertFalse(EducationApplication.objects.exists())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_existing_queue_schedule_and_budget_are_untouched(self):
        OrmQ.objects.create(key="default", payload="existing-opaque-task")
        Schedule.objects.create(
            name="existing", func="education.tasks.enqueue_consultation_reminder_emails"
        )
        MailSendBudget.objects.create(next_allowed_at=self.now)
        models = (OrmQ, Schedule, MailSendBudget, get_user_model())
        before = [list(model.objects.values()) for model in models]
        self.seed()
        self.assertEqual([list(model.objects.values()) for model in models], before)

    def test_invalid_samples_fail_before_media_or_db_writes(self):
        original = json.loads(
            seed_educations.APPLICATION_PRESET_PATH.read_text(encoding="utf-8")
        )
        source = self.media / "invalid.json"
        for error in (
            "duplicate",
            "status",
            "email",
            "future",
            "consultation",
            "correction",
            "mail",
        ):
            records = json.loads(json.dumps(original))
            if error == "duplicate":
                records[-1]["request_id"] = records[0]["request_id"]
            elif error == "status":
                records[-1]["status"] = "invalid"
            elif error == "email":
                records[-1]["email"] = "private@invalid.org"
            elif error == "future":
                records[-1]["created_days_ago"] = -2
            elif error == "consultation":
                records[-1]["consultations"][0]["hours_after_application"] = -1
            elif error == "correction":
                records[1]["consultations"][1]["corrects"] = 10
            else:
                records[-1]["email_state"] = "accepted"
            source.write_text(json.dumps(records), encoding="utf-8")
            with (
                self.subTest(error=error),
                patch.object(seed_educations, "APPLICATION_PRESET_PATH", source),
                self.assertRaises(CommandError),
            ):
                self.seed()
            self.assertFalse(Education.objects.exists())
            self.assertFalse(list(self.media.rglob("*.png")))

    def test_mid_save_failure_rolls_back_all_new_data(self):
        """한 건 저장 후의 실패가 이번 실행의 교육·신청·종속 기록까지 취소하게 한다."""
        targets = (
            ConsultationRecord,
            EducationApplicationReminderEmail,
            MailAttempt,
            EducationApplication.history.model,
        )
        for target in targets:
            original_save = target.save
            count = 0

            def fail_second(instance, *args, **kwargs):
                nonlocal count
                count += 1
                if count == 2:
                    raise DatabaseError("private@example.com confidential DB failure")
                return original_save(instance, *args, **kwargs)

            with (
                self.subTest(model=target.__name__),
                patch.object(target, "save", fail_second),
            ):
                errors = StringIO()
                with self.assertRaises(CommandError) as caught:
                    self.seed(stderr=errors)
                self.assertNotIn("private@example.com", str(caught.exception))
                self.assertFalse(Education.objects.exists())
                self.assertFalse(EducationApplication.objects.exists())
                self.assertFalse(ConsultationRecord.objects.exists())
                self.assertFalse(EducationApplicationReminderEmail.objects.exists())
                self.assertFalse(MailAttempt.objects.exists())
                self.assertEqual(EducationApplication.history.count(), 0)

    def test_request_id_collision_rolls_back_without_overwrite(self):
        from education.tests.test_notifications import notification

        records = json.loads(
            seed_educations.APPLICATION_PRESET_PATH.read_text(encoding="utf-8")
        )
        general = notification().application
        general.request_id = records[-1]["request_id"]
        # 별도 새 일반 신청으로 고정 식별자의 충돌을 만든다.
        general.pk = None
        general._state.adding = True
        general.save()
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(self.snapshot(), before)

    def test_existing_worker_recovers_and_processes_sample_states(self):
        """만료 queued 3건·sending 2건을 복구하고 실제 task로 도래 대상만 모의 처리한다."""
        from education.tasks import send_consultation_reminder_email
        from education.tasks.reminder_dispatch import (
            recover_stale_batch,
            register_due_batch,
        )

        self.seed()
        sending = list(
            EducationApplicationReminderEmail.objects.filter(
                state="sending"
            ).values_list("pk", flat=True)
        )
        terminals = list(
            EducationApplicationReminderEmail.objects.filter(
                application__status__in=EducationApplication.TERMINAL_STATUSES
            )
            .order_by("pk")
            .values()
        )
        with patch("botocore.client.BaseClient._make_api_call") as aws:
            self.assertEqual(recover_stale_batch(self.now), 5)
            self.assertEqual(
                EducationApplicationReminderEmail.objects.filter(
                    pk__in=sending, state="unknown"
                ).count(),
                2,
            )
            self.assertEqual(
                MailAttempt.objects.filter(
                    notification_id__in=sending, state="unknown"
                ).count(),
                2,
            )
            self.assertEqual(
                EducationApplicationReminderEmail.objects.filter(
                    state="queued"
                ).count(),
                0,
            )
            count = register_due_batch(self.now)
            self.assertGreater(count, 3)
            self.assertEqual(OrmQ.objects.count(), count)
            ids = list(
                EducationApplicationReminderEmail.objects.filter(
                    state="queued"
                ).values_list("pk", flat=True)
            )
            for pk in ids:
                self.assertEqual(send_consultation_reminder_email(pk), "simulated")
            aws.assert_not_called()
        self.assertEqual(
            EducationApplicationReminderEmail.objects.filter(
                pk__in=ids, state="simulated"
            ).count(),
            count,
        )
        self.assertEqual(
            list(
                EducationApplicationReminderEmail.objects.filter(
                    application__status__in=EducationApplication.TERMINAL_STATUSES
                )
                .order_by("pk")
                .values()
            ),
            terminals,
        )
        self.assertTrue(
            EducationApplicationReminderEmail.objects.filter(
                state="retry_wait", next_retry_at__gt=self.now
            ).exists()
        )
        self.assertTrue(
            EducationApplicationReminderEmail.objects.filter(
                state="pending", due_at__gt=self.now
            ).exists()
        )
