"""기본 admin의 정보·상담·이력과 URL/POST 우회 권한을 실제 ORM으로 검증한다."""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_q.models import Schedule

from education.models import (
    ConsultationRecord,
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
    MailAttempt,
    MailSendBudget,
)
from education.services.applications import save_application
from education.tests.test_notifications import notification


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            "super", password="test-only-password"
        )
        cls.reader = get_user_model().objects.create_user("reader", is_staff=True)
        cls.reader.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_educationapplication", "view_consultationrecord"]
            )
        )
        cls.editor = get_user_model().objects.create_user("editor", is_staff=True)
        cls.editor.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "view_educationapplication",
                    "change_educationapplication",
                    "view_consultationrecord",
                    "add_consultationrecord",
                ]
            )
        )
        cls.staff = get_user_model().objects.create_user("staff", is_staff=True)
        cls.outsider = get_user_model().objects.create_user("outsider")

    def setUp(self):
        self.row = notification()
        self.application = self.row.application
        self.client.force_login(self.superuser)
        self.url = reverse(
            "admin:education_educationapplication_change", args=[self.application.pk]
        )

    def payload(self, **changes):
        data = {
            field: getattr(self.application, field) or ""
            for field in (
                "name",
                "email",
                "postal_code",
                "address",
                "address_detail",
                "contact_date",
                "status",
                "cancellation_reason",
            )
        }
        data.update({"next_contact_at_0": "", "next_contact_at_1": "", "_save": "저장"})
        # 등록된 inline의 실제 prefix를 사용해 중복 모델 inline도 함께 검증한다.
        page = self.client.get(self.url)
        for inline in page.context["inline_admin_formsets"]:
            prefix = inline.formset.prefix
            data[f"{prefix}-TOTAL_FORMS"] = "0"
            data[f"{prefix}-INITIAL_FORMS"] = "0"
            data[f"{prefix}-MIN_NUM_FORMS"] = "0"
            data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
        data.update(changes)
        return data

    def add_inline_record(self, payload, **changes):
        page = self.client.get(self.url)
        inline = next(
            item
            for item in page.context["inline_admin_formsets"]
            if item.opts.verbose_name_plural == "새 상담 기록 추가"
        )
        prefix = inline.formset.prefix
        payload[f"{prefix}-TOTAL_FORMS"] = "1"
        payload.update(
            {
                f"{prefix}-0-{field}": value
                for field, value in {
                    "result": "unreachable",
                    "content": "부재중, 다시 연락",
                    "corrects": "",
                    **changes,
                }.items()
            }
        )
        return payload

    def test_registration_search_read_only_and_preservation(self):
        for model in (
            Education,
            EducationApplication,
            ConsultationRecord,
            EducationApplicationReminderEmail,
            MailAttempt,
            MailSendBudget,
            Schedule,
            get_user_model(),
        ):
            self.assertTrue(admin.site.is_registered(model))
        listing = reverse("admin:education_educationapplication_changelist")
        response = self.client.get(listing, {"q": self.application.email})
        self.assertContains(response, self.application.email)
        self.assertEqual(
            self.client.get(listing, {"q": "missing@example.com"})
            .context["cl"]
            .result_count,
            0,
        )
        for name, args in (("add", []), ("delete", [self.application.pk])):
            url = reverse(f"admin:education_educationapplication_{name}", args=args)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.post(
            listing,
            {"action": "delete_selected", "_selected_action": str(self.application.pk)},
        )
        self.assertTrue(
            EducationApplication.objects.filter(pk=self.application.pk).exists()
        )

    def test_edit_inline_history_and_original_fields(self):
        payload = self.add_inline_record(
            self.payload(
                name="정정 신청자",
                status="follow_up",
                next_contact_at_0=str(timezone.localdate() + timedelta(days=2)),
                next_contact_at_1="14:00:00",
            )
        )
        payload["request_id"] = "변조"
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(
            (self.application.name, self.application.status),
            ("정정 신청자", "follow_up"),
        )
        record = ConsultationRecord.objects.get()
        self.assertEqual(
            (record.author_id, record.next_contact_at),
            (self.superuser.pk, self.application.next_contact_at),
        )
        history = self.application.history.latest()
        self.assertEqual(history.history_user_id, self.superuser.pk)
        history_url = reverse(
            "admin:education_educationapplication_history", args=[self.application.pk]
        )
        self.assertContains(self.client.get(history_url), "정정 신청자")
        detail = reverse(
            "admin:education_educationapplication_simple_history",
            args=[self.application.pk, history.history_id],
        )
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, payload).status_code, 403)
        self.assertEqual(self.application.history.count(), 2)

    def test_permissions_on_application_record_and_history(self):
        record = ConsultationRecord.objects.create(
            application=self.application,
            author=self.superuser,
            result="consulted",
            content="상담 비공개 내용",
        )
        history_url = reverse(
            "admin:education_educationapplication_history", args=[self.application.pk]
        )
        record_url = reverse(
            "admin:education_consultationrecord_change", args=[record.pk]
        )
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for user in (self.outsider, self.staff):
            self.client.force_login(user)
            for url in (self.url, history_url, record_url):
                self.assertIn(self.client.get(url).status_code, (302, 403))
        self.client.force_login(self.reader)
        self.assertContains(self.client.get(record_url), "상담 비공개 내용")
        self.assertEqual(self.client.get(history_url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"name": "거부"}).status_code, 403)
        self.assertEqual(
            self.client.post(record_url, {"content": "덮어쓰기"}).status_code, 403
        )
        self.client.force_login(self.editor)
        page = self.client.get(self.url)
        self.assertNotContains(page, 'id="id_notification-0-state"')
        self.assertEqual(
            self.client.post(self.url, self.payload(address="정정 주소")).status_code,
            302,
        )
        record.refresh_from_db()
        self.assertEqual(record.content, "상담 비공개 내용")

    def test_standalone_record_requires_parent_permission_and_is_append_only(self):
        self.staff.user_permissions.add(
            Permission.objects.get(codename="view_consultationrecord")
        )
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(
                reverse("admin:education_consultationrecord_changelist")
            ).status_code,
            403,
        )
        self.client.force_login(self.editor)
        url = reverse("admin:education_consultationrecord_add")
        response = self.client.post(
            url,
            {
                "application": self.application.pk,
                "result": "consulted",
                "content": "상담 내용",
                "corrects": "",
                "author": self.staff.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        record = ConsultationRecord.objects.get()
        self.assertEqual(record.author_id, self.editor.pk)
        self.assertEqual(
            self.client.post(
                reverse("admin:education_consultationrecord_delete", args=[record.pk]),
                {},
            ).status_code,
            403,
        )

    def test_correction_and_cross_application_rejection(self):
        record = ConsultationRecord.objects.create(
            application=self.application,
            author=self.superuser,
            result="consulted",
            content="최초 기록",
        )
        payload = self.add_inline_record(
            self.payload(),
            result="correction",
            content="정정 내용",
            corrects=str(record.pk),
        )
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.assertEqual(ConsultationRecord.objects.filter(corrects=record).count(), 1)
        foreign = ConsultationRecord.objects.create(
            application=notification().application,
            author=self.superuser,
            result="consulted",
            content="다른 신청 비공개",
        )
        payload = self.add_inline_record(
            self.payload(), result="correction", corrects=str(foreign.pk)
        )
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ConsultationRecord.objects.filter(application=self.application).count(), 2
        )
        self.assertNotContains(response, "다른 신청 비공개")

    def test_validation_and_record_failure_roll_back_application(self):
        for changes, field in (
            ({"postal_code": "12"}, "postal_code"),
            ({"email": "invalid"}, "email"),
            ({"status": "cancelled"}, "cancellation_reason"),
            ({"contact_date": "2000-01-01"}, "contact_date"),
        ):
            response = self.client.post(self.url, self.payload(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context["adminform"].form.errors)
        payload = self.add_inline_record(self.payload(status="consulting"))
        with patch.object(
            ConsultationRecord, "save", side_effect=RuntimeError("record")
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, payload)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "received")
        self.assertEqual(self.application.history.count(), 1)

    def test_follow_up_filters_and_completion(self):
        now = timezone.now()
        today = timezone.localtime(now).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        past = today - timedelta(days=1)
        future = today + timedelta(days=1)
        for scheduled in (today, past, future, None):
            application = notification().application
            application.status, application.next_contact_at = "follow_up", scheduled
            application.save()
        listing = reverse("admin:education_educationapplication_changelist")
        with patch("education.admin.timezone.now", return_value=today):
            for value, count in (("today", 1), ("overdue", 1), ("undated", 1)):
                self.assertEqual(
                    self.client.get(listing, {"follow_up": value})
                    .context["cl"]
                    .result_count,
                    count,
                )
        save_application(
            self.application.pk,
            {"status": "follow_up", "next_contact_at": future},
            self.superuser,
        )
        self.application.refresh_from_db()
        self.assertEqual(
            self.client.post(self.url, self.payload(status="completed")).status_code,
            302,
        )
        self.application.refresh_from_db()
        self.assertIsNone(self.application.next_contact_at)

    def test_internal_models_reject_all_writes_and_display_mode(self):
        for model in (EducationApplicationReminderEmail, MailAttempt, MailSendBudget):
            prefix = f"admin:education_{model._meta.model_name}"
            self.assertEqual(
                self.client.get(reverse(prefix + "_changelist")).status_code, 200
            )
            self.assertEqual(
                self.client.post(reverse(prefix + "_add"), {}).status_code, 403
            )
        self.assertEqual(
            self.client.post(
                reverse(
                    "admin:education_educationapplicationreminderemail_change",
                    args=[self.row.pk],
                ),
                {"state": "accepted"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "admin:education_educationapplicationreminderemail_delete",
                    args=[self.row.pk],
                ),
                {},
            ).status_code,
            403,
        )
        self.assertContains(self.client.get(self.url), "개발 모의 처리")

    def test_education_admin_validation_acceptance_and_media_identity(self):
        media = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.client.force_login(self.superuser)
        url = reverse("admin:education_education_add")
        payload = {
            "slug": "admin-course",
            "title": "관리 교육",
            "summary": "교육 소개",
            "image": SimpleUploadedFile(
                "example.png", b"test-image", content_type="image/png"
            ),
            "image_alt": "교육 이미지",
            "goals": "목표\n두 번째 목표",
            "audiences": "학생",
            "curriculum-TOTAL_FORMS": "1",
            "curriculum-INITIAL_FORMS": "0",
            "curriculum-0-periods": "1",
            "curriculum-0-period": "1",
            "curriculum-0-topic": "주제",
            "curriculum-0-activity": "활동",
            "curriculum-0-description": "설명",
            "operation_type": "instructor_led",
            "operation_note": "",
            "display_order": "0",
            "is_accepting_inquiries": "on",
            "_save": "저장",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        education = Education.objects.get(slug="admin-course")
        self.assertTrue((Path(media) / education.image.name).exists())
        self.assertEqual(education.goals, ["목표", "두 번째 목표"])
        self.assertEqual(education.curriculum[0]["lessons"][0]["topic"], "주제")
        page = self.client.get(
            reverse("admin:education_education_change", args=[education.pk])
        )
        self.assertContains(page, 'name="curriculum-0-topic"')
        self.assertNotContains(page, '<textarea name="curriculum"')
        self.assertContains(page, "js/education-admin.js")
        identifier = education.media_id
        payload.pop("image")
        payload.pop("is_accepting_inquiries")
        url = reverse("admin:education_education_change", args=[education.pk])
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        education.refresh_from_db()
        self.assertFalse(education.is_accepting_inquiries)
        self.assertEqual(education.media_id, identifier)
        self.assertEqual(
            self.client.get("/api/educations/admin-course/").json()[
                "is_accepting_inquiries"
            ],
            False,
        )
        payload["curriculum-0-periods"] = "2"
        response = self.client.post(url, payload)
        self.assertIn("curriculum", response.context["adminform"].form.errors)
        self.assertEqual(
            self.client.post(
                reverse("admin:education_education_delete", args=[education.pk]), {}
            ).status_code,
            403,
        )
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(url, payload).status_code, 403)
