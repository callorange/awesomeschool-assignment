"""상담 안내 이메일과 미참조 교육 이미지 정리의 Q2 진입점을 제공한다."""

from time import monotonic

from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django_q.tasks import async_task

from .models import ApplicationNotification, Education
from .tasks_support import consultation_reminder_delivery as reminder_delivery
from .tasks_support import consultation_reminder_dispatch as reminder_dispatch
from .tasks_support.exceptions import SafeTaskError

State = ApplicationNotification.State
DISPATCH_SECONDS = 20


def enqueue_consultation_reminder_emails():
    """오래된 작업 복구 후 실행 예산 안에서 등록하고 신규 등록 건수를 반환한다.

    실행 예산만 소진한 경우 후속 검사 하나를 등록한다. 큐가 차면 후속 작업을
    반복 생성하지 않고 다음 정기 검사를 기다린다. 후속 등록 실패 시에도 대상은
    DB에 남아 정기 검사로 복구되며 예외는 Q2에 전달한다.
    """
    deadline = monotonic() + DISPATCH_SECONDS
    now = timezone.now()
    while monotonic() < deadline:
        if not reminder_dispatch.recover_stale_batch(now):
            break
    else:
        async_task(
            "education.tasks.enqueue_consultation_reminder_emails", ack_failure=True
        )
        return 0
    registered = 0
    while monotonic() < deadline:
        count = reminder_dispatch.register_due_batch(timezone.now())
        registered += count
        if count == 0:
            return registered
    with transaction.atomic():
        now = timezone.now()
        if (
            ApplicationNotification.objects.filter(state=State.QUEUED).count()
            < reminder_dispatch.MAIL_QUEUE_LIMIT
            and ApplicationNotification.objects.filter(due_at__lte=now)
            .filter(
                Q(state=State.PENDING)
                | Q(state=State.RETRY_WAIT, next_retry_at__lte=now)
            )
            .exists()
        ):
            async_task(
                "education.tasks.enqueue_consultation_reminder_emails", ack_failure=True
            )
    return registered


def send_consultation_reminder_email(notification_id):
    """처리권을 확보한 안내 하나를 발송하고 안전한 결과를 영속 기록한다.

    Q2의 메일 실패 재전달 대신 상태·허용 시각을 통해 선별 재시도한다. 외부
    전송 후 결과 저장이 실패하면 sending을 남겨 복구 검사에서 unknown으로
    보존한다. 새 외부 호출을 정당화할 증거가 없으므로 즉시 재발송하지 않는다.

    Returns:
        저장한 처리 상태 또는 처리권을 확보하지 못한 경우 "skipped".

    Raises:
        SafeTaskError: 확정 실패·결과 불명 또는 결과 저장 실패. 개인정보와
            provider 예외 원문 대신 시도 식별자와 안전한 오류 코드만 전달한다.
    """
    row = reminder_delivery.claim(notification_id)
    if row is None:
        return "skipped"
    delay = None
    try:
        message = reminder_delivery.build_message(row.application)
        state, code, message_id = reminder_delivery.classify_result(
            message.send(fail_silently=False), message, row.mode
        )
    except Exception as error:
        if row.mode == ApplicationNotification.Mode.SES:
            state, code, delay = reminder_delivery.classify_error(
                error, row.attempt_count
            )
        else:
            state, code = State.FAILED, "simulation_failed"
        message_id = ""
    try:
        reminder_delivery.record_result(
            row.pk, row.attempt_id, state, code, message_id, delay
        )
    except Exception:
        raise SafeTaskError(f"mail:{row.attempt_id}:result_store_failed") from None
    if state in (State.FAILED, State.UNKNOWN):
        raise SafeTaskError(f"mail:{row.attempt_id}:{code}") from None
    return state


def delete_unreferenced_education_image(name, storage_alias="default", using="default"):
    """현재 DB 참조를 재확인한 뒤 지정된 Storage의 미참조 파일만 삭제한다.

    Args:
        name: Storage 기준 상대 파일 키. 큐에는 파일 객체 대신 이 키를 저장한다.
        storage_alias: storages에서 선택할 저장소 alias.
        using: 교육 참조를 조회할 DB alias.

    Returns:
        참조가 있거나 키가 비어 있으면 "preserved", 삭제 요청 완료 시 "deleted".
        이미 없는 파일의 성공 처리는 각 Storage.delete 계약을 따른다.

    Raises:
        SafeTaskError: 저장소 삭제 실패. Q2 제한 재시도를 위해 예외를 전달하되
            원문 대신 파일 키와 예외 종류만 남긴다.
    """
    if not name or Education.objects.using(using).filter(image=name).exists():
        return "preserved"
    try:
        storages[storage_alias].delete(name)
    except Exception as error:
        raise SafeTaskError(f"media:{name}:{type(error).__name__}") from None
    return "deleted"
