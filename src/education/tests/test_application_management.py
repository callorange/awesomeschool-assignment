"""실제 PostgreSQL에서 신청 보존·상담 누적·이력·안내와의 정합성을 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from education.models import (
    ConsultationRecord,
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
)
from education.services.applications import save_application
from education.tasks import (
    enqueue_consultation_reminder_emails,
    send_consultation_reminder_email,
)
from education.tasks.reminder_delivery import claim
from education.tasks.reminder_dispatch import recover_stale_batch
from education.tests.test_notifications import notification


class ApplicationManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("consultant")
        self.row = notification()
        self.application = self.row.application

    def change(self, **values):
        return save_application(self.application.pk, values, self.user)

    def record(self, **values):
        return ConsultationRecord.objects.create(
            application=self.application,
            author=self.user,
            **{"result": "unreachable", "content": "부재중, 다음에 연락", **values},
        )

    def test_preservation_and_append_only_corrections(self):
        original = self.record()
        correction = self.record(
            result="correction", content="오전 통화 기록 정정", corrects=original
        )
        self.assertEqual(correction.corrects_id, original.pk)
        for target in (
            self.application,
            EducationApplication.objects.all(),
            original,
            ConsultationRecord.objects.all(),
        ):
            with self.subTest(target=type(target)), self.assertRaises(ValidationError):
                target.delete()
        original.content = "덮어쓰기"
        with self.assertRaises(ValidationError):
            original.save()
        with self.assertRaises(ValidationError):
            ConsultationRecord.objects.filter(pk=original.pk).update(content="변경")
        with self.assertRaises(ValidationError):
            self.record(result="correction")
        other = notification().application
        with self.assertRaises(ValidationError):
            ConsultationRecord.objects.create(
                application=other,
                author=self.user,
                result="correction",
                content="다른 신청",
                corrects=original,
            )
        self.assertEqual(
            ConsultationRecord.objects.get(pk=original.pk).content,
            "부재중, 다음에 연락",
        )

    def test_snapshot_and_history_are_atomic_and_identify_actor(self):
        snapshot = self.application.submission_snapshot.copy()
        saved = self.change(name="정정 이름", status="consulting")
        self.assertEqual(saved.submission_snapshot, snapshot)
        history = saved.history.latest()
        self.assertEqual(history.history_user_id, self.user.pk)
        self.assertEqual(history.prev_record.name, self.application.name)
        self.assertEqual(history.name, "정정 이름")
        saved.submission_snapshot = {}
        with self.assertRaises(ValidationError):
            saved.save()
        count = saved.history.count()
        with patch(
            "simple_history.models.HistoricalRecords.create_historical_record",
            side_effect=RuntimeError("history"),
        ):
            with self.assertRaises(RuntimeError):
                self.change(name="저장되면 안 됨")
        saved.refresh_from_db()
        self.assertEqual(saved.name, "정정 이름")
        self.assertEqual(saved.history.count(), count)

    def test_follow_up_dates_reason_and_return_to_active(self):
        day = self.application.contact_date
        later = timezone.now() + timedelta(days=1)
        saved = self.change(status="follow_up", next_contact_at=later)
        self.assertEqual(saved.contact_date, day)
        self.assertEqual(saved.next_contact_at, later)
        with self.assertRaises(ValidationError):
            self.change(next_contact_at=timezone.now() - timedelta(hours=1))
        with self.assertRaises(ValidationError):
            self.change(status="cancelled")
        with self.assertRaises(ValidationError):
            self.change(postal_code="abcd")
        saved = self.change(
            status="cancelled", cancellation_reason="진행하지 않기로 합의"
        )
        self.assertIsNone(saved.next_contact_at)
        self.assertEqual(saved.history.latest().prev_record.next_contact_at, later)
        self.row.refresh_from_db()
        self.assertEqual(self.row.state, "suppressed")
        self.change(status="consulting")
        self.assertEqual(enqueue_consultation_reminder_emails(), 0)
        self.assertEqual(send_consultation_reminder_email(self.row.pk), "skipped")

    def test_expired_unchanged_dates_can_be_preserved(self):
        past = timezone.now() - timedelta(days=2)
        self.application.contact_date = past.date()
        self.application.status = "follow_up"
        self.application.next_contact_at = past
        self.application.save()
        saved = self.change(address="정정 주소")
        self.assertEqual(saved.next_contact_at, past)
        self.assertEqual(saved.contact_date, past.date())
        with self.assertRaises(ValidationError):
            self.change(contact_date=past.date() - timedelta(days=1))

    def test_pending_date_email_and_retry_budget_preservation(self):
        future = timezone.localdate() + timedelta(days=2)
        for state in ("pending", "queued", "retry_wait"):
            row = notification(
                state=state,
                attempt_count=1,
                next_retry_at=timezone.now() + timedelta(days=3),
            )
            retry_at = row.next_retry_at
            save_application(
                row.application_id,
                {"email": "corrected@example.com", "contact_date": future},
                self.user,
            )
            row.refresh_from_db()
            self.assertEqual(timezone.localtime(row.due_at).date(), future)
            self.assertEqual(timezone.localtime(row.due_at).hour, 9)
            self.assertEqual((row.attempt_count, row.next_retry_at), (1, retry_at))
            self.assertIsNone(claim(row.pk))
            self.assertEqual(row.application.email, "corrected@example.com")

    def test_sending_restrictions_and_terminal_evidence(self):
        self.row.state = "queued"
        self.row.save()
        self.assertIsNotNone(claim(self.row.pk))
        for values in (
            {"name": "변경"},
            {"email": "other@example.com"},
            {"contact_date": timezone.localdate() + timedelta(days=1)},
            {"status": "completed"},
            {"status": "cancelled", "cancellation_reason": "취소"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.change(**values)
        saved = self.change(
            address="변경 주소",
            status="follow_up",
            next_contact_at=timezone.now() + timedelta(days=1),
        )
        self.assertEqual(saved.address, "변경 주소")
        for state in ("accepted", "simulated", "unknown", "failed"):
            self.row.state, self.row.ses_message_id = state, "evidence"
            self.row.save()
            self.change(status="completed", name="정정")
            self.row.refresh_from_db()
            self.assertEqual(
                (self.row.state, self.row.ses_message_id), (state, "evidence")
            )
        self.assertEqual(send_consultation_reminder_email(self.row.pk), "skipped")

    def test_queued_and_retry_suppression_survives_recovery(self):
        for state in ("pending", "queued", "retry_wait"):
            row = notification(
                state=state,
                queued_at=timezone.now() - timedelta(hours=1),
                attempt_count=1,
            )
            save_application(row.application_id, {"status": "completed"}, self.user)
            row.refresh_from_db()
            self.assertEqual((row.state, row.attempt_count), ("suppressed", 1))
            self.assertIsNone(row.queued_at)
            self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")
        recover_stale_batch(timezone.now())
        self.assertEqual(
            EducationApplicationReminderEmail.objects.filter(
                state="suppressed"
            ).count(),
            3,
        )

    def test_corrected_recipient_is_used_by_actual_mock_delivery(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.change(
            email="corrected@example.com", contact_date=tomorrow, name="정정 신청자"
        )
        self.row.refresh_from_db()
        self.row.state = "queued"
        self.row.save()
        with patch(
            "education.tasks.reminder_delivery.timezone.now",
            return_value=self.row.due_at + timedelta(seconds=1),
        ):
            self.assertEqual(send_consultation_reminder_email(self.row.pk), "simulated")
        self.assertEqual(mail.outbox[-1].to, ["corrected@example.com"])
        self.assertIn("정정 신청자", mail.outbox[-1].body)

    def test_notification_or_record_failure_rolls_back_whole_change(self):
        count = self.application.history.count()
        with patch.object(
            EducationApplicationReminderEmail,
            "save",
            side_effect=RuntimeError("notice"),
        ):
            with self.assertRaises(RuntimeError):
                self.change(status="completed")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "received")
        self.assertEqual(self.application.history.count(), count)
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.change(status="consulting")
            self.record()
            raise RuntimeError("record transaction")
        self.assertFalse(ConsultationRecord.objects.exists())
        self.assertEqual(self.application.history.count(), count)

    def test_education_deletion_preserves_consultation_and_records_detachment(self):
        education = Education.objects.create(slug="history-course", title="원본 교육")
        self.application.education = education
        self.application.save()
        record = self.record()
        count = self.application.history.count()
        education_id = education.pk
        education.delete()
        self.application.refresh_from_db()
        self.assertIsNone(self.application.education_id)
        self.assertTrue(ConsultationRecord.objects.filter(pk=record.pk).exists())
        self.assertEqual(self.application.history.count(), count + 1)
        history = self.application.history.latest()
        self.assertEqual(history.prev_record.education_id, education_id)
        self.assertIsNone(history.education_id)
        self.assertEqual(history.history_change_reason, "원본 교육 삭제로 연결 해제")


class ManagementClaimRaceTests(TransactionTestCase):
    def test_cancel_commits_before_waiting_worker_claim(self):
        row = notification(state="queued")
        started, release = Event(), Event()

        def cancel():
            close_old_connections()
            try:
                with transaction.atomic():
                    save_application(
                        row.application_id,
                        {"status": "cancelled", "cancellation_reason": "취소 합의"},
                        None,
                    )
                    started.set()
                    if not release.wait(10):
                        raise RuntimeError("관리 저장 대기 만료")
            finally:
                close_old_connections()

        def worker():
            close_old_connections()
            try:
                return send_consultation_reminder_email(row.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            management = pool.submit(cancel)
            try:
                self.assertTrue(started.wait(5))
                sending = pool.submit(worker)
            finally:
                release.set()
            management.result(10)
            self.assertEqual(sending.result(10), "skipped")
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("suppressed", 0))
        self.assertFalse(row.attempts.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_worker_claim_precedes_waiting_cancellation(self):
        row = notification(state="queued")
        claimed, release = Event(), Event()

        def worker():
            close_old_connections()
            try:
                with transaction.atomic():
                    self.assertIsNotNone(claim(row.pk))
                    claimed.set()
                    if not release.wait(10):
                        raise RuntimeError("처리권 대기 만료")
            finally:
                close_old_connections()

        def cancel():
            close_old_connections()
            try:
                with self.assertRaises(ValidationError):
                    save_application(
                        row.application_id,
                        {"status": "cancelled", "cancellation_reason": "취소"},
                        None,
                    )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            sending = pool.submit(worker)
            try:
                self.assertTrue(claimed.wait(5))
                cancellation = pool.submit(cancel)
            finally:
                release.set()
            sending.result(10)
            cancellation.result(10)
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("sending", 1))
        self.assertEqual(
            EducationApplication.objects.get(pk=row.application_id).status, "received"
        )
