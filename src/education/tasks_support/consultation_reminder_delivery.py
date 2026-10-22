"""상담 안내 이메일 task의 전송 처리권·메일 구성·결과 기록을 지원한다."""

from datetime import timedelta
from time import monotonic, sleep

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import ApplicationNotification, MailAttempt, MailSendBudget

State = ApplicationNotification.State


def claim(notification_id):
    """짧은 row lock으로 예산과 전송 처리권을 확보한 안내를 반환한다.

    전송 전에 MailAttempt·현재 시도 식별자·횟수를 같은 transaction에 commit한다.
    공유 예산 대기는 lock 밖에서 최대 5초 수행하고 더 길면 retry_wait로 보존한다.
    예산 대기·중복 전달·환경 불일치 등 전송하지 않는 경우 None을 반환한다.
    """
    deadline = monotonic() + 5
    while True:
        wait = 0
        with transaction.atomic():
            row = (
                ApplicationNotification.objects.select_for_update()
                .select_related("application")
                .filter(pk=notification_id)
                .first()
            )
            now = timezone.now()
            if (
                row is None
                or row.state != State.QUEUED
                or row.due_at > now
                or row.attempt_count >= 3
                or (row.next_retry_at and row.next_retry_at > now)
            ):
                return None
            if row.mode != settings.NOTIFICATION_MODE:
                row.state, row.error_code = State.FAILED, "environment_mismatch"
                row.save(update_fields=["state", "error_code"])
                return None
            if row.mode == ApplicationNotification.Mode.SES:
                budget, _ = MailSendBudget.objects.select_for_update().get_or_create(
                    pk=1
                )
                wait = max(0, (budget.next_allowed_at - now).total_seconds())
                if wait > max(0, deadline - monotonic()):
                    row.state, row.next_retry_at = (
                        State.RETRY_WAIT,
                        budget.next_allowed_at,
                    )
                    row.save(update_fields=["state", "next_retry_at"])
                    return None
                if not wait:
                    budget.next_allowed_at = now + timedelta(
                        seconds=1 / settings.SES_MAX_SEND_RATE
                    )
                    budget.save(update_fields=["next_allowed_at"])
            if not wait:
                attempt = MailAttempt.objects.create(notification=row, started_at=now)
                row.state, row.attempt_id, row.started_at = (
                    State.SENDING,
                    attempt.pk,
                    now,
                )
                row.attempt_count += 1
                row.error_code, row.queued_at = "", None
                row.save(
                    update_fields=[
                        "state",
                        "attempt_id",
                        "started_at",
                        "attempt_count",
                        "error_code",
                        "queued_at",
                    ]
                )
                return row
        sleep(wait)


def record_result(
    notification_id, attempt_id, state, code="", message_id="", delay=None
):
    """현재 시도의 안내·시도 결과를 함께 저장하고 오래된 결과는 무시한다.

    현재 attempt_id의 sending에만 반영하되 같은 시도의 SES 성공 증거는 unknown도
    accepted로 복구할 수 있다. 늦은 실패가 완료 상태를 덮어쓰지는 않는다.
    재시도 시각은 이 결과 기록 시각부터 delay만큼 계산한다.
    """
    with transaction.atomic():
        row = ApplicationNotification.objects.select_for_update().get(
            pk=notification_id
        )
        if row.attempt_id != attempt_id:
            return
        allowed = (
            [State.SENDING, State.UNKNOWN]
            if state == State.ACCEPTED
            else [State.SENDING]
        )
        if row.state not in allowed:
            return
        now = timezone.now()
        row.state, row.error_code, row.ses_message_id = state, code, message_id
        row.next_retry_at = now + delay if state == State.RETRY_WAIT else None
        if state == State.ACCEPTED:
            row.sent_at = now
        elif state == State.SIMULATED:
            row.simulated_at = now
        row.save(
            update_fields=[
                "state",
                "error_code",
                "ses_message_id",
                "next_retry_at",
                "sent_at",
                "simulated_at",
            ]
        )
        MailAttempt.objects.filter(pk=attempt_id, notification=row).update(
            state=state, error_code=code, ses_message_id=message_id, finished_at=now
        )


def build_message(application):
    """신청 당시 snapshot으로 HTML·텍스트 메일을 생성하며 실제 전송은 하지 않는다.

    주소 등 상담에 불필요한 개인정보는 본문에서 제외한다. 제목의 줄바꿈을
    제거하고 HTML 본문의 사용자 입력은 template의 기본 escaping을 따른다.
    """
    context = {"application": application}
    title = " ".join(application.education_title.splitlines())
    message = EmailMultiAlternatives(
        subject=f"[히어로스쿨] {title} 상담 신청 안내",
        body=render_to_string("education/mail/application.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[application.email],
    )
    message.attach_alternative(
        render_to_string("education/mail/application.html", context), "text/html"
    )
    return message


def classify_error(error, attempt_count):
    """미접수 증거가 있는 오류만 재시도하며 알 수 없는 결과는 unknown으로 반환한다.

    Args:
        error: SES backend 또는 SDK에서 발생한 예외. 원문은 저장·로그에 전달하지 않는다.
        attempt_count: 방금 실패한 시도를 포함한 누적 횟수. 오류 종류가 바뀌어도 유지한다.

    Returns:
        (상태, 안전한 오류 코드, 재시도 지연). 지연은 외부 호출 실패에만 적용한다.
    """
    # 개발 경로에서 AWS SDK를 로딩하거나 credential을 조회하지 않는다.
    from botocore.exceptions import (
        ClientError,
        ConnectTimeoutError,
        EndpointConnectionError,
        NoCredentialsError,
        NoRegionError,
        ParamValidationError,
        PartialCredentialsError,
    )

    if isinstance(
        error,
        (
            NoCredentialsError,
            PartialCredentialsError,
            NoRegionError,
            ParamValidationError,
        ),
    ):
        return State.FAILED, "ses_configuration", None
    delay = None
    code = "unconfirmed_error"
    if isinstance(error, (ConnectTimeoutError, EndpointConnectionError)):
        code, delay = (
            "connection_not_established",
            timedelta(minutes=5 if attempt_count == 1 else 15),
        )
    elif isinstance(error, ClientError):
        detail = error.response.get("Error", {})
        provider_code = detail.get("Code", "")
        if provider_code in {
            "Throttling",
            "ThrottlingException",
            "TooManyRequestsException",
        }:
            reason = detail.get("Message", "").strip().casefold()
            if reason == "daily message quota exceeded":
                code, delay = "daily_quota", timedelta(hours=24)
            elif reason == "maximum sending rate exceeded":
                code, delay = (
                    "send_rate",
                    timedelta(minutes=5 if attempt_count == 1 else 15),
                )
        elif provider_code in {
            "MessageRejected",
            "MailFromDomainNotVerifiedException",
            "BadRequestException",
            "AccessDenied",
            "AccessDeniedException",
            "InvalidClientTokenId",
            "SignatureDoesNotMatch",
            "AccountSuspendedException",
            "SendingPausedException",
            "ValidationError",
            "InvalidParameterValue",
        }:
            return State.FAILED, "ses_rejected", None
    if delay is not None:
        return (State.RETRY_WAIT if attempt_count < 3 else State.FAILED), code, delay
    return State.UNKNOWN, code, None


def classify_result(count, message, mode):
    """고정 backend의 반환·접수 증거로 모의 완료와 실제 SES 접수를 구분한다.

    SES는 반환 1과 같은 message의 MessageId가 함께 있어야 accepted다. 확실한
    미전송 0 이외의 불일치는 unknown으로 보존하며 전달 완료로 추정하지 않는다.

    Returns:
        (처리 상태, 안전한 오류 코드, SES MessageId). 접수 증거가 없으면 ID는 빈 값이다.
    """
    message_id = message.extra_headers.get("message_id", "")
    if count == 1:
        if mode == ApplicationNotification.Mode.SIMULATED:
            return State.SIMULATED, "", ""
        if isinstance(message_id, str) and 0 < len(message_id) <= 255:
            return State.ACCEPTED, "", message_id
    # 잠근 SES backend는 미전송을 0으로 반환하고 외부 호출 오류는 예외로 전달한다.
    if count == 0 and not message_id and message.extra_headers.get("status") != 200:
        return State.FAILED, "backend_not_sent", ""
    return State.UNKNOWN, "invalid_send_result", ""
