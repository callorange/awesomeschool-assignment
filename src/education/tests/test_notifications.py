"""실제 ORM 상태 전이·큐 기록·개발 backend와 운영 SES 경계를 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import Mock, patch
from uuid import uuid4

from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, ReadTimeoutError
from django.core import mail
from django.core.management import call_command
from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_q.models import OrmQ, Schedule
from django_q.signing import SignedPackage

from education.models import (
    EducationApplication,
    EducationApplicationReminderEmail,
    MailAttempt,
    MailSendBudget,
)
from education.tasks import (
    enqueue_consultation_reminder_emails,
    reminder_delivery,
    send_consultation_reminder_email,
)
from education.tasks.exceptions import SafeTaskError


def notification(**fields):
    """개인정보 노출·escaping 검사용 신청과 기본적으로 기한이 지난 안내를 DB에 생성한다."""
    application = EducationApplication.objects.create(
        education_slug="course",
        education_title="교육 <b>제목</b>",
        request_id=uuid4(),
        name="신청자 <script>",
        email="person@example.com",
        postal_code="04524",
        address="민감한 주소",
        contact_date=timezone.localdate(),
    )
    return EducationApplicationReminderEmail.objects.create(
        application=application,
        **dict(
            {"due_at": timezone.now() - timedelta(minutes=1), "mode": "simulated"},
            **fields,
        ),
    )


class NotificationTests(TestCase):
    def test_due_and_multiple_batches_are_ordered_without_duplicate_registration(self):
        first = notification()
        first.due_at -= timedelta(days=1)
        first.save()
        later = [notification() for _ in range(100)]
        future = notification(due_at=timezone.now() + timedelta(days=1))
        self.assertEqual(enqueue_consultation_reminder_emails(), 101)
        rows = list(OrmQ.objects.order_by("pk"))
        package = SignedPackage.loads(rows[0].payload)
        self.assertEqual(package["args"], (first.pk,))
        self.assertEqual(
            package["func"], "education.tasks.send_consultation_reminder_email"
        )
        self.assertTrue(package["ack_failure"])
        self.assertEqual(enqueue_consultation_reminder_emails(), 0)
        self.assertEqual(OrmQ.objects.count(), 101)
        future.refresh_from_db()
        self.assertEqual(future.state, "pending")
        self.assertEqual(sum(row.attempt_count for row in later), 0)

    def test_dispatch_capacity_and_enqueue_failure_preserve_targets(self):
        with patch("education.tasks.reminder_dispatch.MAIL_QUEUE_LIMIT", 2):
            rows = [notification() for _ in range(3)]
            self.assertEqual(enqueue_consultation_reminder_emails(), 2)
            self.assertEqual(
                EducationApplicationReminderEmail.objects.filter(
                    state="pending"
                ).count(),
                1,
            )
        OrmQ.objects.all().delete()
        EducationApplicationReminderEmail.objects.all().update(
            state="pending", queued_at=None
        )
        with patch(
            "education.tasks.reminder_dispatch.async_task",
            side_effect=RuntimeError("queue unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                enqueue_consultation_reminder_emails()
        self.assertFalse(OrmQ.objects.exists())
        self.assertEqual(
            EducationApplicationReminderEmail.objects.filter(state="pending").count(),
            len(rows),
        )
        self.assertEqual(enqueue_consultation_reminder_emails(), 3)

    def test_dispatch_budget_creates_one_continuation(self):
        notification()
        with patch("education.tasks.reminders.monotonic", side_effect=[0, 0, 21]):
            self.assertEqual(enqueue_consultation_reminder_emails(), 0)
        package = SignedPackage.loads(OrmQ.objects.get().payload)
        self.assertEqual(
            package["func"], "education.tasks.enqueue_consultation_reminder_emails"
        )
        self.assertEqual(enqueue_consultation_reminder_emails(), 1)

    def test_failed_continuation_is_recovered_by_next_periodic_dispatch(self):
        row = notification()
        with (
            patch("education.tasks.reminders.monotonic", side_effect=[0, 0, 21]),
            patch(
                "education.tasks.reminders.async_task",
                side_effect=RuntimeError("queue"),
            ),
            self.assertRaises(RuntimeError),
        ):
            enqueue_consultation_reminder_emails()
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("pending", 0))
        self.assertFalse(OrmQ.objects.exists())
        self.assertEqual(enqueue_consultation_reminder_emails(), 1)

    def test_batch_selection_and_continuation_use_the_same_due_conditions(self):
        now = timezone.now()
        past, future = now - timedelta(days=1), now + timedelta(days=1)
        for state, due_at, retry_at, continuation in (
            ("pending", future, None, False),
            ("retry_wait", past, future, False),
            ("retry_wait", future, past, False),
            ("retry_wait", past, past, True),
            ("pending", past, None, True),
        ):
            with (
                self.subTest(state=state, due_at=due_at, retry_at=retry_at),
                transaction.atomic(),
            ):
                OrmQ.objects.all().delete()
                first = notification(due_at=past - timedelta(days=1))
                waiting = notification(
                    state=state, due_at=due_at, next_retry_at=retry_at
                )
                with (
                    patch(
                        "education.tasks.reminder_dispatch.BATCH_SIZE",
                        1,
                    ),
                    patch(
                        "education.tasks.reminders.monotonic", side_effect=[0, 0, 0, 21]
                    ),
                ):
                    self.assertEqual(enqueue_consultation_reminder_emails(), 1)
                packages = [
                    SignedPackage.loads(row.payload)
                    for row in OrmQ.objects.order_by("pk")
                ]
                self.assertEqual(packages[0]["args"], (first.pk,))
                self.assertEqual(len(packages), 2 if continuation else 1)
                if continuation:
                    self.assertEqual(
                        packages[1]["func"],
                        "education.tasks.enqueue_consultation_reminder_emails",
                    )
                    self.assertTrue(packages[1]["ack_failure"])
                waiting.refresh_from_db()
                self.assertEqual(waiting.state, state)
                self.assertEqual(
                    enqueue_consultation_reminder_emails(), int(continuation)
                )
                transaction.set_rollback(True)

    def test_simulation_is_once_and_does_not_contact_aws(self):
        row = notification(state="queued", queued_at=timezone.now())
        with patch("boto3.Session", side_effect=AssertionError("AWS access")):
            self.assertEqual(send_consultation_reminder_email(row.pk), "simulated")
            self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("simulated", 1))
        self.assertIsNotNone(row.simulated_at)
        self.assertIsNone(row.sent_at)
        self.assertEqual(row.ses_message_id, "")
        self.assertEqual(MailAttempt.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("민감한 주소", mail.outbox[0].body)
        self.assertIn("&lt;script&gt;", mail.outbox[0].alternatives[0].content)
        self.assertIn("상담 후 협의", mail.outbox[0].body)
        self.assertNotIn("오늘", mail.outbox[0].body)

    def test_stale_queued_recovers_but_stale_sending_does_not_resend(self):
        queued = notification(
            state="queued", queued_at=timezone.now() - timedelta(minutes=11)
        )
        sending = notification(state="queued", queued_at=timezone.now())
        claimed = reminder_delivery.claim(sending.pk)
        EducationApplicationReminderEmail.objects.filter(pk=sending.pk).update(
            started_at=timezone.now() - timedelta(minutes=11)
        )
        self.assertEqual(enqueue_consultation_reminder_emails(), 1)
        queued.refresh_from_db()
        sending.refresh_from_db()
        self.assertEqual(queued.state, "queued")
        self.assertEqual(sending.state, "unknown")
        self.assertEqual(send_consultation_reminder_email(sending.pk), "skipped")
        reminder_delivery.record_result(
            sending.pk, claimed.attempt_id, "accepted", message_id="late-success"
        )
        reminder_delivery.record_result(
            sending.pk, claimed.attempt_id, "failed", "late-failure"
        )
        reminder_delivery.record_result(sending.pk, uuid4(), "failed", "wrong-attempt")
        sending.refresh_from_db()
        self.assertEqual(
            (sending.state, sending.ses_message_id), ("accepted", "late-success")
        )

    def test_success_recording_is_atomic_and_failure_is_safe(self):
        row = notification(state="queued", queued_at=timezone.now())
        with patch(
            "education.tasks.reminder_delivery.MailAttempt.objects.filter",
            side_effect=RuntimeError("private-data"),
        ):
            with self.assertRaises(SafeTaskError) as error:
                send_consultation_reminder_email(row.pk)
        self.assertNotIn("private-data", str(error.exception))
        row.refresh_from_db()
        self.assertEqual(row.state, "sending")
        self.assertIsNone(row.simulated_at)
        self.assertEqual(MailAttempt.objects.get().state, "sending")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")

    def test_schedule_is_idempotent_and_status_has_no_private_data(self):
        row = notification(state="unknown")
        output = StringIO()
        for _ in range(2):
            call_command("configure_background_tasks", stdout=output)
        schedule = Schedule.objects.get()
        self.assertEqual(
            (schedule.minutes, schedule.func, schedule.cluster),
            (5, "education.tasks.enqueue_consultation_reminder_emails", "default"),
        )
        call_command("notification_status", stdout=output)
        text = output.getvalue()
        self.assertIn("unknown: 1", text)
        self.assertNotIn(row.application.name, text)
        self.assertNotIn(row.application.email, text)
        self.assertNotIn(row.application.address, text)

    def test_existing_schedule_changes_function_without_replacing_row_or_next_run(self):
        next_run = timezone.now() + timedelta(hours=1)
        existing = Schedule.objects.create(
            name="education-notifications",
            func="education.tasks.dispatch_notifications",
            schedule_type=Schedule.HOURLY,
            repeats=0,
            next_run=next_run,
            cluster="default",
        )
        for _ in range(2):
            call_command("configure_background_tasks", stdout=StringIO())
        existing.refresh_from_db()
        self.assertEqual(Schedule.objects.get().pk, existing.pk)
        self.assertEqual(existing.next_run, next_run)
        self.assertEqual(
            existing.func, "education.tasks.enqueue_consultation_reminder_emails"
        )
        self.assertEqual(
            (
                existing.schedule_type,
                existing.minutes,
                existing.repeats,
                existing.cluster,
            ),
            (Schedule.MINUTES, 5, -1, "default"),
        )


@override_settings(
    NOTIFICATION_MODE="ses",
    SES_MAX_SEND_RATE=1000,
    USE_SES_V2=True,
    AWS_SES_AUTO_THROTTLE=None,
    AWS_SES_REGION_NAME="ap-northeast-2",
    AWS_SES_CONFIG=Config(
        connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1}
    ),
    MAILERS={"default": {"BACKEND": "django_ses.SESBackend"}},
)
class SESNotificationTests(TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.send_email.return_value = {
            "MessageId": "ses-123",
            "ResponseMetadata": {"RequestId": "request-123"},
        }
        self.session = self.enterContext(patch("django_ses.boto3.Session"))
        self.session.return_value.client.return_value = self.client

    def test_real_ses_backend_records_message_id_and_uses_one_sdk_call(self):
        row = notification(mode="ses", state="queued", queued_at=timezone.now())
        self.assertEqual(send_consultation_reminder_email(row.pk), "accepted")
        self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")
        row.refresh_from_db()
        self.assertEqual(
            (row.state, row.ses_message_id, row.attempt_count),
            ("accepted", "ses-123", 1),
        )
        self.assertIsNotNone(row.sent_at)
        self.assertIsNone(row.simulated_at)
        self.client.send_email.assert_called_once()
        self.assertIn("Raw", self.client.send_email.call_args.kwargs["Content"])
        self.assertEqual(
            self.session.return_value.client.call_args.kwargs["config"].retries[
                "total_max_attempts"
            ],
            1,
        )

    def test_timeout_and_missing_message_id_are_unknown_without_private_error(self):
        for error in (
            ReadTimeoutError(endpoint_url="https://secret.example"),
            KeyError("private-data"),
        ):
            row = notification(mode="ses", state="queued", queued_at=timezone.now())
            self.client.send_email.side_effect = error
            with self.assertRaises(SafeTaskError) as caught:
                send_consultation_reminder_email(row.pk)
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn("private-data", str(caught.exception))
            row.refresh_from_db()
            self.assertEqual(row.state, "unknown")
            self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")

    def test_rate_retry_intervals_and_mixed_error_attempt_limit(self):
        row = notification(mode="ses", state="queued", queued_at=timezone.now())
        start = timezone.now()
        MailSendBudget.objects.create(next_allowed_at=start - timedelta(seconds=1))
        for index, (reason, delay) in enumerate(
            [
                ("Maximum sending rate exceeded", timedelta(minutes=5)),
                ("Daily message quota exceeded", timedelta(hours=24)),
                ("Maximum sending rate exceeded", None),
            ],
            start=1,
        ):
            self.client.send_email.side_effect = ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": reason}},
                "SendEmail",
            )
            if index > 1:
                start = row.next_retry_at
                EducationApplicationReminderEmail.objects.filter(pk=row.pk).update(
                    state="queued", queued_at=start
                )
            with patch(
                "education.tasks.reminder_delivery.timezone.now",
                return_value=start,
            ):
                if index < 3:
                    self.assertEqual(
                        send_consultation_reminder_email(row.pk), "retry_wait"
                    )
                else:
                    with self.assertRaises(SafeTaskError):
                        send_consultation_reminder_email(row.pk)
            row.refresh_from_db()
            self.assertEqual(row.attempt_count, index)
            if delay:
                self.assertEqual(row.next_retry_at, start + delay)
                self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")
        self.assertEqual(row.state, "failed")
        self.assertEqual(MailAttempt.objects.count(), 3)

    def test_zero_and_one_without_id_do_not_become_success(self):
        for count, state in ((0, "failed"), (1, "unknown")):
            row = notification(mode="ses", state="queued", queued_at=timezone.now())
            with (
                patch("django.core.mail.EmailMessage.send", return_value=count),
                self.assertRaises(SafeTaskError),
            ):
                send_consultation_reminder_email(row.pk)
            row.refresh_from_db()
            self.assertEqual(row.state, state)

    def test_configuration_and_permanent_rejections_do_not_retry(self):
        for error in (
            NoCredentialsError(),
            ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "private-provider-detail",
                    }
                },
                "SendEmail",
            ),
        ):
            row = notification(mode="ses", state="queued", queued_at=timezone.now())
            self.client.send_email.side_effect = error
            with self.assertRaises(SafeTaskError) as caught:
                send_consultation_reminder_email(row.pk)
            row.refresh_from_db()
            self.assertEqual(row.state, "failed")
            self.assertIsNone(row.next_retry_at)
            self.assertNotIn("private-provider-detail", str(caught.exception))

    def test_second_transient_error_uses_fifteen_minute_delay(self):
        error = ClientError(
            {
                "Error": {
                    "Code": "ThrottlingException",
                    "Message": "Maximum sending rate exceeded",
                }
            },
            "SendEmail",
        )
        state, code, delay = reminder_delivery.classify_error(error, 2)
        self.assertEqual(
            (state, code, delay), ("retry_wait", "send_rate", timedelta(minutes=15))
        )

    def test_shared_budget_defers_without_consuming_attempt(self):
        row = notification(mode="ses", state="queued", queued_at=timezone.now())
        budget = MailSendBudget.objects.create(
            next_allowed_at=timezone.now() + timedelta(minutes=1)
        )
        self.assertEqual(send_consultation_reminder_email(row.pk), "skipped")
        row.refresh_from_db()
        self.assertEqual(
            (row.state, row.attempt_count, row.next_retry_at),
            ("retry_wait", 0, budget.next_allowed_at),
        )
        self.assertFalse(MailAttempt.objects.exists())
        self.client.send_email.assert_not_called()


class ConcurrentNotificationTests(TransactionTestCase):
    def test_two_workers_use_one_claim_and_one_locmem_send(self):
        row = notification(state="queued", queued_at=timezone.now())
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return send_consultation_reminder_email(row.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: run(), range(2)))
        self.assertEqual(sorted(results), ["simulated", "skipped"])
        row.refresh_from_db()
        self.assertEqual(row.attempt_count, 1)
        self.assertEqual(MailAttempt.objects.count(), 1)

    @override_settings(NOTIFICATION_MODE="ses", SES_MAX_SEND_RATE=0.01)
    def test_separate_connections_share_budget(self):
        rows = [
            notification(mode="ses", state="queued", queued_at=timezone.now())
            for _ in range(2)
        ]
        barrier = Barrier(2)

        def claim(pk):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return reminder_delivery.claim(pk) is not None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, [row.pk for row in rows]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(MailSendBudget.objects.count(), 1)
        self.assertEqual(MailAttempt.objects.count(), 1)
        self.assertEqual(
            EducationApplicationReminderEmail.objects.filter(
                state="retry_wait", attempt_count=0
            ).count(),
            1,
        )
