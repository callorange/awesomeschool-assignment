"""격리된 PostgreSQL과 미디어에서 실제 qcluster 프로세스와 결과 flush를 검증한다."""

import os
import signal
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from django_q.models import Failure, OrmQ, Success
from django_q.tasks import async_task

from education.models import Education, EducationApplicationReminderEmail, MailAttempt
from education.tests.test_notifications import notification


class QClusterProcessTests(TransactionTestCase):
    def setUp(self):
        self.media = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=self.media))
        self.environment = {
            **os.environ,
            "EDUCATION_TEST_DB": connection.settings_dict["NAME"],
            "EDUCATION_TEST_MEDIA": str(self.media),
        }

    def run_once(self):
        """공개 run-once 명령의 정상 종료와 결과 저장이 끝날 때까지 기다린다."""
        result = subprocess.run(
            [
                sys.executable,
                str(settings.BASE_DIR / "manage.py"),
                "qcluster",
                "--run-once",
                "--settings=education.tests.worker_settings",
            ],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_application_to_simulated_mail_and_image_cleanup_flush_before_exit(self):
        row = notification()
        name = default_storage.save("education/worker.png", ContentFile(b"image"))
        education = Education.objects.create(slug="worker", image=name)
        education.delete()
        async_task("education.tasks.enqueue_consultation_reminder_emails")
        for _ in range(6):
            self.run_once()
            if not OrmQ.objects.exists():
                break
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("simulated", 1))
        self.assertIsNotNone(row.simulated_at)
        self.assertFalse(default_storage.exists(name))
        self.assertFalse(OrmQ.objects.exists())
        self.assertEqual(Success.objects.count(), 3)
        self.assertFalse(Failure.objects.exists())

    def test_forced_worker_stop_preserves_unknown_and_recovers_unattempted_queue(self):
        row = notification(state="queued", queued_at=timezone.now())
        async_task("education.tasks.send_consultation_reminder_email", row.pk)
        marker = self.media / "sending.flag"
        process = subprocess.Popen(
            [
                sys.executable,
                str(settings.BASE_DIR / "manage.py"),
                "qcluster",
                "--settings=education.tests.worker_settings",
            ],
            env={**self.environment, "EDUCATION_TEST_SENDING": str(marker)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        try:
            deadline = monotonic() + 20
            while not marker.exists() and monotonic() < deadline:
                sleep(0.05)
            self.assertTrue(marker.exists(), "worker가 전송 경계에 도달하지 못함")
            row.refresh_from_db()
            self.assertEqual((row.state, row.attempt_count), ("sending", 1))
        finally:
            self.stop_tree(process)
        self.assertIsNotNone(process.returncode)
        past = timezone.now() - timedelta(minutes=11)
        EducationApplicationReminderEmail.objects.filter(pk=row.pk).update(
            started_at=past
        )
        OrmQ.objects.update(lock=past)
        waiting = notification(state="queued", queued_at=past)
        async_task("education.tasks.enqueue_consultation_reminder_emails")
        for _ in range(6):
            self.run_once()
            if not OrmQ.objects.exists():
                break
        row.refresh_from_db()
        waiting.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("unknown", 1))
        self.assertIsNone(row.simulated_at)
        self.assertEqual(MailAttempt.objects.filter(notification=row).count(), 1)
        self.assertEqual((waiting.state, waiting.attempt_count), ("simulated", 1))
        self.assertFalse(OrmQ.objects.exists())

    def test_dispatch_budget_continuation_runs_with_the_new_task_path(self):
        row = notification()
        async_task("education.tests.worker_settings.exhaust_dispatch_budget")
        for _ in range(6):
            self.run_once()
            if not OrmQ.objects.exists():
                break
        row.refresh_from_db()
        self.assertEqual((row.state, row.attempt_count), ("simulated", 1))
        self.assertEqual(MailAttempt.objects.filter(notification=row).count(), 1)
        self.assertFalse(OrmQ.objects.exists())
        self.assertTrue(
            Success.objects.filter(
                func="education.tasks.enqueue_consultation_reminder_emails"
            ).exists()
        )
        self.assertTrue(
            Success.objects.filter(
                func="education.tasks.send_consultation_reminder_email"
            ).exists()
        )
        self.assertFalse(Failure.objects.exists())

    def stop_tree(self, process):
        """이 테스트가 시작한 qcluster의 프로세스 트리만 종료하고 pipe를 회수한다."""
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=True,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=15)

    def test_failed_image_can_be_requeued_after_storage_problem_is_fixed(self):
        name = "education/blocked.png"
        blocked = self.media / name
        blocked.mkdir(parents=True)
        child = blocked / "keep.txt"
        child.write_text("test fixture", encoding="utf-8")
        async_task(
            "education.tasks.delete_unreferenced_education_image",
            name,
            "default",
            "default",
            ack_failure=False,
        )
        for _ in range(3):
            self.run_once()
            if Failure.objects.exists():
                break
        failure = Failure.objects.get()
        self.assertIn("SafeTaskError", str(failure.result))
        self.assertTrue(child.exists())
        child.unlink()
        async_task(failure.func, *failure.args, **failure.kwargs, ack_failure=False)
        for _ in range(3):
            self.run_once()
            if not blocked.exists():
                break
        self.assertFalse(blocked.exists())
        self.assertTrue(
            Success.objects.filter(
                func="education.tasks.delete_unreferenced_education_image"
            ).exists()
        )
