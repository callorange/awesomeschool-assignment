"""관리 입력 검증과 신청·안내의 단일 transaction 저장 경계를 정의한다."""

from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import EducationApplication, EducationApplicationReminderEmail

EDITABLE_FIELDS = (
    "name",
    "email",
    "postal_code",
    "address",
    "address_detail",
    "contact_date",
    "status",
    "next_contact_at",
    "cancellation_reason",
)
PENDING_STATES = (
    EducationApplicationReminderEmail.State.PENDING,
    EducationApplicationReminderEmail.State.QUEUED,
    EducationApplicationReminderEmail.State.RETRY_WAIT,
)


def validate_change(application, values, notification):
    """상태에 맞게 입력을 정리하고 날짜·발송 중 변경 제한을 검증한다.

    values는 개별 필드 검증을 마친 값이며 이 함수가 직접 수정한다. 재연락·취소
    상태를 벗어나면 각각 다음 연락 예정·취소 사유를 비운다. 기존 기한 경과 값은
    다른 정보 정정을 막지 않도록 유지하고 새로 바꾼 일정만 과거 여부를 검사한다.
    DB에는 저장하지 않으며 검증 실패 전에도 values의 정리가 적용될 수 있다.

    Raises:
        ValidationError: 위반한 필드별 오류. 호출자는 해당 변경을 저장하지 않아야 한다.
    """
    errors = {}
    status = values.get("status", application.status)
    if status != EducationApplication.Status.FOLLOW_UP:
        values["next_contact_at"] = None
    if status != EducationApplication.Status.CANCELLED:
        values["cancellation_reason"] = ""
    elif not values.get("cancellation_reason", application.cancellation_reason).strip():
        errors["cancellation_reason"] = "취소 사유를 입력해 주세요."
    contact_date = values.get("contact_date", application.contact_date)
    if contact_date != application.contact_date and contact_date < timezone.localdate():
        errors["contact_date"] = "변경할 날짜는 오늘 이후로 선택해 주세요."
    next_contact = values.get("next_contact_at", application.next_contact_at)
    if (
        next_contact
        and next_contact != application.next_contact_at
        and next_contact < timezone.now()
    ):
        errors["next_contact_at"] = "새 연락 예정은 현재 이후로 선택해 주세요."
    if notification.state == EducationApplicationReminderEmail.State.SENDING:
        errors.update(
            {
                field: "안내 발송 중입니다. 결과 확인 후 다시 수정해 주세요."
                for field in ("name", "email", "contact_date")
                if values.get(field, getattr(application, field))
                != getattr(application, field)
            }
        )
        if status in EducationApplication.TERMINAL_STATUSES:
            errors["status"] = "안내 발송 중입니다. 결과 확인 후 종료해 주세요."
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def save_application(application_id, values, user):
    """안내→신청 순서로 잠근 뒤 관리값·변경 이력·대상 시각을 함께 저장한다.

    호출자의 오래된 모델 전체를 덮어쓰지 않고 전달된 관리 필드만 적용한다.
    상담 기록을 같이 저장하는 admin 요청은 이 연산을 감싼 transaction을 쓴다.
    발송이 시작되지 않은 안내만 일정 변경·종료 상태에 맞춰 조정하며 이미 남은
    전송 증거는 보존한다. 재연락 일정 변경만으로 안내를 다시 예약하지 않는다.

    Args:
        application_id: 변경할 기존 신청의 PK. 연결된 안내가 생성되어 있어야 한다.
        values: 정규화한 관리 입력. EDITABLE_FIELDS 외 키는 저장하지 않는다.
        user: 변경 이력에 남길 사용자. 시스템 변경은 None을 전달한다.

    Returns:
        검증과 저장을 마친 신청 인스턴스. 값이 같으면 새 변경 이력은 만들지 않는다.

    Raises:
        ValidationError: 입력 또는 상태 변경이 유효하지 않은 경우. 전체 저장은 롤백된다.
    """
    notification = EducationApplicationReminderEmail.objects.select_for_update().get(
        application_id=application_id
    )
    application = EducationApplication.objects.select_for_update().get(
        pk=application_id
    )
    values = {
        field: value for field, value in values.items() if field in EDITABLE_FIELDS
    }
    validate_change(application, values, notification)
    date_changed = (
        values.get("contact_date", application.contact_date) != application.contact_date
    )
    changed = [
        field for field, value in values.items() if getattr(application, field) != value
    ]
    for field in changed:
        setattr(application, field, values[field])
    application.full_clean(exclude=["education", "submission_snapshot"])
    if changed:
        application._history_user = user
        application.save(update_fields=changed)
    if notification.state in PENDING_STATES:
        if application.status in EducationApplication.TERMINAL_STATUSES:
            notification.state = EducationApplicationReminderEmail.State.SUPPRESSED
            notification.queued_at = notification.next_retry_at = None
            notification.save(update_fields=["state", "queued_at", "next_retry_at"])
        elif date_changed:
            notification.due_at = max(
                datetime.combine(
                    application.contact_date,
                    time(9),
                    tzinfo=timezone.get_default_timezone(),
                ),
                application.created_at,
            )
            notification.save(update_fields=["due_at"])
    return application
