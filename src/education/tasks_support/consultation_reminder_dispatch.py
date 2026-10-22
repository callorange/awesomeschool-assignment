"""상담 안내 이메일 등록 task의 오래된 상태 복구와 배치 등록을 지원한다."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django_q.tasks import async_task

from ..models import ApplicationNotification, MailAttempt

State = ApplicationNotification.State
BATCH_SIZE = 100
MAIL_QUEUE_LIMIT = 200
STALE_AFTER = timedelta(minutes=10)


def recover_stale_batch(now):
    """오래된 queued를 pending으로, sending을 unknown으로 최대 한 batch 복구한다.

    큐 재전달은 전송 증거가 아니므로 sending의 횟수를 되돌리거나 재발송하지
    않는다. 처리 중인 다른 transaction의 row는 건너뛰고 복구한 건수를 반환한다.
    """
    stale = now - STALE_AFTER
    with transaction.atomic():
        rows = list(
            ApplicationNotification.objects.select_for_update(skip_locked=True)
            .filter(
                Q(state=State.QUEUED, queued_at__lte=stale)
                | Q(state=State.SENDING, started_at__lte=stale)
            )
            .order_by("pk")[:BATCH_SIZE]
        )
        for row in rows:
            if row.state == State.QUEUED:
                row.state, row.queued_at = State.PENDING, None
                row.save(update_fields=["state", "queued_at"])
            else:
                row.state, row.error_code = State.UNKNOWN, "worker_interrupted"
                row.save(update_fields=["state", "error_code"])
                MailAttempt.objects.filter(
                    pk=row.attempt_id, state=State.SENDING
                ).update(
                    state=State.UNKNOWN, error_code=row.error_code, finished_at=now
                )
    return len(rows)


def register_due_batch(now):
    """대기량 한도 내에서 오래된 대상부터 최대 한 batch를 등록하고 건수를 반환한다.

    skip_locked로 중복 선택을 피하고 안내 상태와 Q2 ORM row를 같은 transaction에
    기록한다. enqueue 실패 시 batch 전체를 rollback하므로 다음 검사에서 재발견한다.
    """
    with transaction.atomic():
        room = (
            MAIL_QUEUE_LIMIT
            - ApplicationNotification.objects.filter(state=State.QUEUED).count()
        )
        if room <= 0:
            return 0
        rows = list(
            ApplicationNotification.objects.filter(due_at__lte=now)
            .filter(
                Q(state=State.PENDING)
                | Q(state=State.RETRY_WAIT, next_retry_at__lte=now)
            )
            .select_for_update(skip_locked=True)
            .order_by("due_at", "pk")[: min(BATCH_SIZE, room)]
        )
        for row in rows:
            async_task(
                "education.tasks.send_consultation_reminder_email",
                row.pk,
                ack_failure=True,
            )
            row.state, row.queued_at = State.QUEUED, now
            row.save(update_fields=["state", "queued_at"])
    return len(rows)
