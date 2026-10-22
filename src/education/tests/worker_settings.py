"""실제 qcluster subprocess를 부모 테스트 DB·임시 미디어에만 연결한다."""

import os
from pathlib import Path
from time import sleep

from django.core.mail.backends.locmem import EmailBackend

from config.settings import dev
from config.settings.dev import *  # noqa: F403

DATABASES = {
    "default": {**dev.DATABASES["default"], "NAME": os.environ["EDUCATION_TEST_DB"]}
}
MEDIA_ROOT = Path(os.environ["EDUCATION_TEST_MEDIA"])
Q_CLUSTER = {**dev.Q_CLUSTER, "poll": 0.05, "scheduler": False, "log_level": "ERROR"}


class BlockingEmailBackend(EmailBackend):
    """외부 전송 경계 진입을 파일로 알리고 강제 종료까지 모의 전송을 대기한다."""

    def send_messages(self, email_messages):
        Path(os.environ["EDUCATION_TEST_SENDING"]).write_text(
            "sending", encoding="utf-8"
        )
        sleep(60)
        return super().send_messages(email_messages)


if os.environ.get("EDUCATION_TEST_SENDING"):
    MAILERS = {
        "default": {"BACKEND": "education.tests.worker_settings.BlockingEmailBackend"}
    }


def exhaust_dispatch_budget():
    """실제 worker에서 검사 시계만 진행시켜 후속 Q2 작업 등록·실행을 검증한다."""
    from unittest.mock import patch

    from education.tasks import enqueue_consultation_reminder_emails

    with patch("education.tasks.reminders.monotonic", side_effect=[0, 0, 21]):
        return enqueue_consultation_reminder_emails()
