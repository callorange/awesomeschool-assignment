"""실제 PostgreSQL에서 접수·중복 제출·CSRF·개인정보 경계를 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from education.models import (
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
    MailAttempt,
    MailSendBudget,
)
from education.serializers import EducationApplicationSerializer


def application_payload(slug="test-course"):
    return {
        "education_slug": slug,
        "name": "홍길동",
        "email": "User@example.com",
        "postal_code": "04524",
        "address": "서울특별시 중구 세종대로 110",
        "contact_date": str(timezone.localdate()),
        "request_id": str(uuid4()),
    }


class ApplicationAPITests(TestCase):
    def setUp(self):
        self.education = Education.objects.create(
            slug="test-course", title="교육", image=""
        )
        self.payload = application_payload()

    def post(self, payload=None, client=None):
        return (client or self.client).post(
            "/api/applications/",
            payload or self.payload,
            content_type="application/json",
        )

    def test_education_get_and_no_application_read_access(self):
        response = self.client.get("/api/educations/test-course/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {
                "slug",
                "title",
                "summary",
                "image_url",
                "image_alt",
                "operation_type",
                "operation_note",
                "is_accepting_inquiries",
            },
        )
        self.assertEqual(self.client.get("/api/educations/missing/").status_code, 404)
        self.assertEqual(self.client.get("/api/applications/").status_code, 405)
        self.assertEqual(self.client.get("/api/applications/1/").status_code, 404)
        for method in ("put", "patch", "delete"):
            self.assertEqual(
                getattr(self.client, method)("/api/applications/").status_code, 405
            )

    def test_initial_state_normalization_and_private_response(self):
        self.payload["name"] = " 홍길동 "
        self.payload["email"] = " User@example.com "
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            {
                "request_id": self.payload["request_id"],
                "status": "received",
                "status_display": "접수",
            },
        )
        application = EducationApplication.objects.get()
        self.assertEqual(
            (application.name, application.email, application.address_detail),
            ("홍길동", "User@example.com", ""),
        )
        notification = application.notification
        self.assertEqual(
            (notification.state, notification.attempt_count), ("pending", 0)
        )
        self.assertEqual(notification.mode, "simulated")
        self.assertIsNone(notification.sent_at)
        self.assertIsNone(notification.attempt_id)
        self.assertIsNone(notification.queued_at)
        self.assertIsNone(notification.simulated_at)
        self.assertEqual(notification.ses_message_id, "")
        self.assertFalse(MailAttempt.objects.exists())
        self.assertGreaterEqual(notification.due_at, application.created_at)

    def test_invalid_fields_and_past_date_do_not_create_rows(self):
        for field, value in (
            ("name", " "),
            ("name", "가" * 101),
            ("email", "invalid"),
            ("postal_code", "1234"),
            ("contact_date", "invalid"),
            ("contact_date", str(timezone.localdate() - timedelta(days=1))),
            ("request_id", "invalid"),
            ("status", "completed"),
        ):
            with self.subTest(field=field, value=value):
                response = self.post(dict(self.payload, **{field: value}))
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(EducationApplication.objects.exists())
        self.assertFalse(EducationApplicationReminderEmail.objects.exists())

    def test_contact_day_morning_and_late_submission_due_times(self):
        zone = ZoneInfo("Asia/Seoul")
        for hour, expected_hour in ((8, 9), (10, 10)):
            with self.subTest(hour=hour):
                created = datetime(2026, 10, 22, hour, tzinfo=zone)
                payload = dict(application_payload(), contact_date="2026-10-22")
                with patch(
                    "education.serializers.timezone.localdate",
                    return_value=created.date(),
                ):
                    serializer = EducationApplicationSerializer(data=payload)
                    serializer.is_valid(raise_exception=True)
                    application = serializer.save(created_at=created)
                self.assertEqual(
                    application.notification.due_at,
                    created.replace(hour=expected_hour),
                )

    def test_notification_and_send_budget_database_constraints(self):
        self.post()
        notification = EducationApplicationReminderEmail.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            EducationApplicationReminderEmail.objects.create(
                application=notification.application,
                due_at=notification.due_at,
                mode="simulated",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            EducationApplicationReminderEmail.objects.filter(pk=notification.pk).update(
                attempt_count=4
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            MailSendBudget.objects.create(id=2)

    def test_repeat_conflict_and_snapshot_after_education_deletion(self):
        self.assertEqual(self.post().status_code, 201)
        application = EducationApplication.objects.get()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(
            self.post(dict(self.payload, name="다른 이름")).status_code, 409
        )
        self.education.slug = "changed"
        self.education.is_accepting_inquiries = False
        self.education.save()
        self.assertEqual(self.post().status_code, 200)
        self.education.delete()
        with patch(
            "education.serializers.timezone.localdate",
            return_value=timezone.localdate() + timedelta(days=2),
        ):
            self.assertEqual(self.post().status_code, 200)
        application.refresh_from_db()
        self.assertIsNone(application.education_id)
        self.assertEqual(application.education_title, "교육")
        self.assertEqual(EducationApplication.objects.count(), 1)
        self.assertEqual(EducationApplicationReminderEmail.objects.count(), 1)

    def test_stopped_missing_and_atomic_notification_failure(self):
        self.assertEqual(
            self.post(dict(self.payload, education_slug="missing")).status_code, 404
        )
        self.education.is_accepting_inquiries = False
        self.education.save()
        self.assertEqual(self.post().status_code, 400)
        self.education.is_accepting_inquiries = True
        self.education.save()
        with patch(
            "education.serializers.EducationApplicationReminderEmail.objects.create",
            side_effect=RuntimeError("failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.post()
        self.assertFalse(EducationApplication.objects.exists())
        self.assertFalse(EducationApplicationReminderEmail.objects.exists())

    def test_csrf_is_enforced_for_anonymous_post(self):
        from django.middleware.csrf import get_token
        from django.test import RequestFactory

        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client=client).status_code, 403)
        token = get_token(RequestFactory().get("/"))
        client.cookies["csrftoken"] = token
        response = client.post(
            "/api/applications/",
            self.payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201)

    def test_original_submission_survives_management_changes_without_disclosure(self):
        from education.services.applications import save_application

        self.assertEqual(self.post().status_code, 201)
        application = EducationApplication.objects.get()
        for status in ("follow_up", "completed", "cancelled"):
            save_application(
                application.pk,
                {
                    "name": "정정 이름",
                    "email": "corrected@example.com",
                    "address": "정정 주소",
                    "contact_date": timezone.localdate() + timedelta(days=1),
                    "status": status,
                    "cancellation_reason": "진행 중단 합의",
                },
                None,
            )
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "request_id": self.payload["request_id"],
                    "status": "received",
                    "status_display": "접수",
                },
            )
            self.assertEqual(
                self.post(dict(self.payload, name="정정 이름")).status_code, 409
            )
            application.refresh_from_db()
            self.assertEqual(
                (application.name, application.status), ("정정 이름", status)
            )
        self.assertEqual(
            (
                EducationApplication.objects.count(),
                EducationApplicationReminderEmail.objects.count(),
            ),
            (1, 1),
        )


class ConcurrentSubmissionTests(TransactionTestCase):
    def test_original_commit_and_stop_between_repeat_lookup_and_education_lock(self):
        Education.objects.create(slug="test-course", title="교육")
        payload = application_payload()
        lookup_done, resume = Event(), Event()

        def repeat():
            close_old_connections()

            def wait_after_lookup(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if (
                    sql.startswith("SELECT")
                    and '"education_educationapplication"' in sql
                    and not lookup_done.is_set()
                ):
                    lookup_done.set()
                    if not resume.wait(timeout=10):
                        raise RuntimeError("동시 제출 검증의 진행 신호 누락")
                return result

            try:
                with connections["default"].execute_wrapper(wait_after_lookup):
                    serializer = EducationApplicationSerializer(data=payload)
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    return serializer.created
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(repeat)
            try:
                self.assertTrue(lookup_done.wait(timeout=5))
                original = EducationApplicationSerializer(data=payload)
                original.is_valid(raise_exception=True)
                original.save()
                Education.objects.filter(slug="test-course").update(
                    is_accepting_inquiries=False
                )
            finally:
                resume.set()
            self.assertFalse(pending.result(timeout=10))
        self.assertEqual(EducationApplication.objects.count(), 1)
        self.assertEqual(EducationApplicationReminderEmail.objects.count(), 1)

    def test_same_submission_in_separate_connections_creates_one_target(self):
        Education.objects.create(slug="test-course", title="교육")
        payload = application_payload()
        barrier = Barrier(2)

        def submit():
            close_old_connections()
            try:
                serializer = EducationApplicationSerializer(data=payload)
                serializer.is_valid(raise_exception=True)
                barrier.wait(timeout=5)
                serializer.save()
                return serializer.created
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(EducationApplication.objects.count(), 1)
        self.assertEqual(EducationApplicationReminderEmail.objects.count(), 1)

    def test_outer_rollback_removes_application_and_target(self):
        Education.objects.create(slug="test-course", title="교육")
        with self.assertRaises(RuntimeError), transaction.atomic():
            serializer = EducationApplicationSerializer(data=application_payload())
            serializer.is_valid(raise_exception=True)
            serializer.save()
            raise RuntimeError("rollback")
        self.assertFalse(EducationApplication.objects.exists())
        self.assertFalse(EducationApplicationReminderEmail.objects.exists())
