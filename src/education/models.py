from uuid import uuid7

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, router, transaction
from django.utils import timezone
from simple_history.models import HistoricalRecords

from .media import education_image_upload_to
from .validators import validate_curriculum, validate_text_list


class Education(models.Model):
    """공개 교육 소개와 저장소에 독립적인 대표 이미지 참조를 보관한다.

    goals와 audiences는 문자열 목록이다. curriculum은 periods(시수)와
    lessons(교시 목록)으로 구성하며, 각 교시는 period·topic·activity·description을
    가진다. full_clean()과 이를 호출하는 프리셋 명령이 JSON 구조를 검증한다.
    save()·QuerySet.update()는 입력 검증을 자동 실행하지 않는다.
    운영 방식과 상담 접수 상태는 신청 입력에서 사용할 값이며,
    접수 중단 상태도 교육 소개는 공개한다. 진행 안내는 일반 텍스트다.
    image는 저장소 상대 이름으로 보관하고 실제 제공 URL은 선택한 Storage가 만든다.
    media_id는 저장 전에 생성하는 UUIDv7이며 slug와 무관한 고정 이미지 폴더다.
    편집 입력에서 제외하고 교육 생성 후에는 변경하지 않는다.
    삭제·일반 save()의 이미지 교체 후 미참조 파일은 commit 이후 정리한다.
    QuerySet.update()·bulk_update()·직접 SQL은 이 파일 정리를 우회한다.
    """

    class OperationType(models.TextChoices):
        """교육 제공 방식을 구분하며 모집 방식이나 일정 확정 상태는 표현하지 않는다."""

        INSTRUCTOR_LED = "instructor_led", "코치 출강"
        COURSEWARE = "courseware", "코스웨어"

    slug = models.SlugField(
        "URL 식별자",
        unique=True,
        help_text="교육 상세 주소에 사용합니다. 변경하면 기존 상세 주소로 접근할 수 없습니다.",
    )
    media_id = models.UUIDField(
        "이미지 폴더 식별자",
        default=uuid7,
        unique=True,
        editable=False,
        help_text="자동 생성되는 UUIDv7입니다. 이미지 폴더를 고정하므로 생성 후 변경하지 않습니다.",
    )
    title = models.CharField("교육명", max_length=100)
    summary = models.CharField("한 줄 소개", max_length=300)
    image = models.FileField(
        "대표 이미지",
        upload_to=education_image_upload_to,
        max_length=255,
        help_text="업로드한 파일은 교육별 UUID 폴더에 저장됩니다.",
    )
    image_alt = models.CharField(
        "이미지 대체 텍스트",
        max_length=200,
        help_text="이미지를 볼 수 없을 때에도 내용을 이해할 수 있도록 설명합니다.",
    )
    goals = models.JSONField(
        "교육 목표",
        default=list,
        validators=[validate_text_list],
        help_text='비어 있지 않은 문자열의 JSON 목록입니다. 예: ["AI 활용 능력 기르기"]',
    )
    audiences = models.JSONField(
        "추천 대상",
        default=list,
        validators=[validate_text_list],
        help_text='비어 있지 않은 문자열의 JSON 목록입니다. 예: ["생성형 AI에 관심 있는 학생"]',
    )
    curriculum = models.JSONField(
        "시수별 커리큘럼",
        default=list,
        validators=[validate_curriculum],
        help_text=(
            "JSON 목록으로 입력합니다. 각 항목의 periods는 총 수업 차시 수, "
            "lessons는 그 수만큼의 교시 목록입니다. 각 교시에는 "
            "period(1부터 연속된 번호), topic(주제), activity(활동명), "
            "description(활동 설명)이 필요하며 periods는 항목 간 중복할 수 없습니다."
        ),
    )
    operation_type = models.CharField(
        "운영 방식",
        max_length=20,
        choices=OperationType.choices,
        default=OperationType.INSTRUCTOR_LED,
        help_text="교육 제공 방식입니다. 기수별 모집이나 일정 확정 여부를 뜻하지 않습니다.",
    )
    operation_note = models.TextField(
        "진행 안내",
        blank=True,
        default="",
        help_text="일정·지역·인원 등 상담에서 협의할 조건을 일반 텍스트로 안내합니다. 생략할 수 있습니다.",
    )
    is_accepting_inquiries = models.BooleanField(
        "상담 접수 가능",
        default=True,
        help_text="해제해도 교육 소개는 공개됩니다. 접수 가능은 수강 확정을 의미하지 않습니다.",
    )
    display_order = models.PositiveSmallIntegerField(
        "표시 순서",
        default=0,
        help_text="작은 값부터 표시하며 같은 값이면 URL 식별자 순으로 정렬합니다.",
    )

    class Meta:
        verbose_name = "교육 정보"
        verbose_name_plural = "교육 정보"
        ordering = ["display_order", "slug"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """이미지 교체와 post_save의 ORM 큐 등록이 함께 commit되게 한다."""
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            return super().save(*args, **kwargs)


class PreservedQuerySet(models.QuerySet):
    """신청과 상담의 일반 ORM 삭제를 차단하며 테스트 DB flush는 방해하지 않는다."""

    def delete(self):
        raise ValidationError("신청과 상담 기록은 삭제할 수 없습니다.")


class ConsultationQuerySet(PreservedQuerySet):
    """기존 상담은 변경하지 않고 새 정정 기록으로 보완한다."""

    def update(self, **kwargs):
        raise ValidationError("기존 상담 기록은 수정할 수 없습니다.")


class EducationApplication(models.Model):
    """교육 삭제 후에도 신청 당시 상담 내용과 제출 식별자를 보존한다.

    education_slug·education_title은 신청 시점의 snapshot이다. 같은 request_id의
    재요청은 현재 교육 정보 대신 저장된 입력과 비교하며 새 신청을 만들지 않는다.
    안내의 발송 상태는 notification에서 관리하고 신청 상태와 구분한다.
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "접수"
        CONSULTING = "consulting", "상담중"
        FOLLOW_UP = "follow_up", "재연락 예정"
        COMPLETED = "completed", "완료"
        CANCELLED = "cancelled", "취소"

    TERMINAL_STATUSES = (Status.COMPLETED, Status.CANCELLED)

    objects = PreservedQuerySet.as_manager()
    history = HistoricalRecords(excluded_fields=["submission_snapshot"])

    submission_snapshot = models.JSONField("최초 제출 입력", editable=False)
    next_contact_at = models.DateTimeField("다음 연락 예정", null=True, blank=True)
    cancellation_reason = models.TextField("취소 사유", blank=True, default="")

    education = models.ForeignKey(
        Education,
        verbose_name="신청 교육",
        null=True,
        on_delete=models.SET_NULL,
        related_name="applications",
        help_text="원본 교육입니다. 교육 삭제 후에도 신청은 남으며 이 참조만 비워집니다.",
    )
    education_slug = models.SlugField(
        "신청 당시 교육 URL 식별자",
        help_text="신청 당시 slug입니다. 교육 변경·삭제 후에도 동일 제출 확인에 사용합니다.",
    )
    education_title = models.CharField(
        "신청 당시 교육명",
        max_length=100,
        help_text="신청 당시 교육명입니다. 이후 교육 정보와 무관하게 안내 메일에 사용합니다.",
    )
    request_id = models.UUIDField(
        "제출 식별자",
        unique=True,
        help_text="클라이언트가 생성한 UUID입니다. 같은 식별자·입력의 재요청은 기존 접수를 반환합니다.",
    )
    name = models.CharField(
        "신청자 이름",
        max_length=100,
        help_text="상담 신청자 이름이며 안내 메일의 인사말에 사용합니다.",
    )
    email = models.EmailField(
        "이메일", max_length=254, help_text="상담 안내 메일을 받을 이메일 주소입니다."
    )
    postal_code = models.CharField(
        "우편번호",
        max_length=5,
        validators=[RegexValidator(r"^[0-9]{5}$", "숫자 5자리를 입력해 주세요.")],
        help_text="주소 검색 또는 직접 입력한 숫자 5자리 우편번호입니다.",
    )
    address = models.CharField(
        "기본주소",
        max_length=255,
        help_text="주소 검색으로 선택하거나 직접 입력한 기본주소입니다.",
    )
    address_detail = models.CharField(
        "상세주소",
        max_length=255,
        blank=True,
        default="",
        help_text="동·호수 등 추가 주소입니다. 입력하지 않으면 빈 문자열로 저장합니다.",
    )
    contact_date = models.DateField(
        "연락 가능 날짜",
        help_text="한국 날짜 기준 상담 연락이 가능한 날입니다. 교육 일정이나 연락 시각을 확정하지 않습니다.",
    )
    status = models.CharField(
        "신청 상태",
        max_length=20,
        choices=Status,
        default=Status.RECEIVED,
        help_text="신규 신청은 접수로 저장합니다. 자동 안내 메일의 처리 상태와는 별개입니다.",
    )
    created_at = models.DateTimeField(
        "신청 일시",
        default=timezone.now,
        editable=False,
        help_text="신청 생성 시각입니다. 연락 가능 날짜의 09시가 지난 신청은 이 시각부터 안내 대상입니다.",
    )

    class Meta:
        verbose_name = "교육 신청"
        verbose_name_plural = "교육 신청"

    def __str__(self):
        return f"신청 {self.pk} · {self.education_title}"

    def delete(self, *args, **kwargs):
        raise ValidationError("신청은 삭제할 수 없습니다.")

    def save(self, *args, **kwargs):
        """최초 제출을 보존하고 신청과 history 저장이 함께 commit되게 한다.

        생성 시 날짜·UUID를 문자열로 정규화한 원본을 저장한다. 이후 원본·제출
        식별자·교육 snapshot·생성 시각은 일반 save로 바꿀 수 없다. QuerySet.update와
        bulk_update·직접 SQL은 이 검증과 일반 변경 이력 포착을 우회한다.
        """
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            if self._state.adding:
                self.submission_snapshot = {
                    field: str(getattr(self, field))
                    for field in (
                        "education_slug",
                        "name",
                        "email",
                        "postal_code",
                        "address",
                        "address_detail",
                        "contact_date",
                        "request_id",
                    )
                }
            else:
                original = type(self).objects.using(using).get(pk=self.pk)
                if any(
                    getattr(self, field) != getattr(original, field)
                    for field in (
                        "submission_snapshot",
                        "request_id",
                        "education_slug",
                        "education_title",
                        "created_at",
                    )
                ):
                    raise ValidationError("최초 제출 정보는 변경할 수 없습니다.")
            return super().save(*args, **kwargs)


class ConsultationRecord(models.Model):
    """상담 당시의 결과·일정과 정정 대상을 덮어쓰지 않고 누적한다."""

    class Result(models.TextChoices):
        CONSULTED = "consulted", "상담 진행"
        UNREACHABLE = "unreachable", "부재중"
        RESCHEDULED = "rescheduled", "재연락 합의"
        CORRECTION = "correction", "정정"

    objects = ConsultationQuerySet.as_manager()
    application = models.ForeignKey(
        EducationApplication,
        on_delete=models.PROTECT,
        related_name="consultations",
        verbose_name="교육 신청",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="작성자",
        editable=False,
    )
    created_at = models.DateTimeField("작성 시각", default=timezone.now, editable=False)
    result = models.CharField("연락 결과", max_length=20, choices=Result)
    content = models.TextField("상담 내용")
    next_contact_at = models.DateTimeField(
        "당시 다음 연락 예정",
        null=True,
        blank=True,
        editable=False,
    )
    corrects = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
        verbose_name="정정 대상",
    )

    class Meta:
        verbose_name = "상담 기록"
        verbose_name_plural = "상담 기록"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"상담 기록 {self.pk} · {self.get_result_display()}"

    def clean(self):
        super().clean()
        if not self.content.strip():
            raise ValidationError({"content": "상담 내용을 입력해 주세요."})
        if self.result == self.Result.CORRECTION:
            if not self.corrects_id:
                raise ValidationError({"corrects": "정정할 원기록을 선택해 주세요."})
            if self.corrects.application_id != self.application_id:
                raise ValidationError(
                    {"corrects": "같은 신청의 기록만 정정할 수 있습니다."}
                )
        elif self.corrects_id:
            raise ValidationError(
                {"corrects": "정정 결과에서만 원기록을 지정할 수 있습니다."}
            )

    def save(self, *args, **kwargs):
        """새 상담만 검증 후 추가하며 기존 PK를 가진 새 인스턴스의 덮어쓰기도 막는다."""
        if not self._state.adding or (
            self.pk is not None and type(self).objects.filter(pk=self.pk).exists()
        ):
            raise ValidationError(
                "기존 상담 기록은 수정할 수 없습니다. 정정을 추가해 주세요."
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("상담 기록은 삭제할 수 없습니다.")


class EducationApplicationReminderEmail(models.Model):
    """큐 재전달과 실제 메일 전송 시도를 구분하는 신청별 영속 처리 기록이다.

    신청과 같은 transaction에 pending·시도 0으로 생성한다. worker는 처리권과
    시도 기록을 commit한 뒤 전송하며 accepted·simulated는 재전송하지 않는다.
    unknown은 미발송을 뜻하지 않으므로 시간 경과만으로 재시도하지 않는다.
    """

    class State(models.TextChoices):
        PENDING = "pending", "발송 대기"
        QUEUED = "queued", "큐 대기"
        SENDING = "sending", "발송 시도 중"
        ACCEPTED = "accepted", "SES 접수"
        SIMULATED = "simulated", "모의 완료"
        RETRY_WAIT = "retry_wait", "재시도 대기"
        FAILED = "failed", "실패"
        UNKNOWN = "unknown", "결과 확인 필요"
        SUPPRESSED = "suppressed", "발송 중단"

    class Mode(models.TextChoices):
        SIMULATED = "simulated", "개발 모의 처리"
        SES = "ses", "운영 SES"

    application = models.OneToOneField(
        EducationApplication,
        verbose_name="교육 신청",
        on_delete=models.CASCADE,
        related_name="notification",
        help_text="신청마다 하나만 생성하는 자동 안내입니다. 신청 삭제 시 함께 삭제됩니다.",
    )
    due_at = models.DateTimeField(
        "안내 대상 시작 일시",
        help_text="연락 가능 날짜의 한국 시각 09시와 신청 일시 중 늦은 값입니다. 실제 발송 시각은 아닙니다.",
    )
    mode = models.CharField(
        "전송 모드",
        max_length=10,
        choices=Mode,
        help_text="생성 당시의 개발 모의 처리 또는 운영 SES 모드입니다. 환경이 달라지면 전송하지 않습니다.",
    )
    state = models.CharField(
        "안내 처리 상태",
        max_length=20,
        choices=State,
        default=State.PENDING,
        help_text="미시도는 pending입니다. accepted는 SES 접수이며 수신함 도착을 보장하지 않습니다.",
    )
    queued_at = models.DateTimeField(
        "큐 등록 일시",
        null=True,
        blank=True,
        help_text="현재 작업의 큐 등록 시각입니다. 오래된 미시도 작업 복구에 사용하고 처리권 확보 시 비웁니다.",
    )
    next_retry_at = models.DateTimeField(
        "다음 처리 허용 일시",
        null=True,
        blank=True,
        help_text="재시도 또는 공유 전송 예산 대기의 최소 허용 시각입니다. 다음 검사·큐 대기로 지연될 수 있습니다.",
    )
    attempt_count = models.PositiveSmallIntegerField(
        "전송 시도 횟수",
        default=0,
        help_text="처리권을 확보한 전송 시도 수이며 최대 3회입니다. 큐 재전달·예산 대기는 증가시키지 않습니다.",
    )
    attempt_id = models.UUIDField(
        "현재 전송 시도 식별자",
        null=True,
        blank=True,
        help_text="현재 MailAttempt의 UUID입니다. 시도 전에는 비어 있고 이전 시도의 결과 갱신을 막습니다.",
    )
    started_at = models.DateTimeField(
        "현재 전송 시도 시작 일시",
        null=True,
        blank=True,
        help_text="현재 처리권을 확보한 시각입니다. 오래된 sending을 unknown으로 복구하는 기준입니다.",
    )
    simulated_at = models.DateTimeField(
        "모의 처리 완료 일시",
        null=True,
        blank=True,
        help_text="개발 locmem 처리 완료 시각입니다. 외부 발송이나 SES 접수를 의미하지 않습니다.",
    )
    sent_at = models.DateTimeField(
        "SES 접수 확인 일시",
        null=True,
        blank=True,
        help_text="SES 접수 성공을 기록한 시각입니다. 미시도·모의 처리·결과 불명은 비워 두며 실제 전달 시각은 아닙니다.",
    )
    ses_message_id = models.CharField(
        "SES 메시지 식별자",
        max_length=255,
        blank=True,
        default="",
        help_text="SES 접수 성공 응답의 MessageId입니다. 미접수·모의 처리·결과 불명에는 비워 둡니다.",
    )
    error_code = models.CharField(
        "안전한 오류 코드",
        max_length=64,
        blank=True,
        default="",
        help_text="분류된 오류 코드만 저장합니다. 수신자·본문·provider 예외 원문은 기록하지 않습니다.",
    )

    class Meta:
        verbose_name = "상담 안내 이메일"
        verbose_name_plural = "상담 안내 이메일"
        indexes = [
            models.Index(fields=["state", "due_at"], name="notification_due_idx"),
            models.Index(
                fields=["state", "next_retry_at"], name="notification_retry_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempt_count__lte=3),
                name="notification_max_attempts",
            )
        ]


class MailAttempt(models.Model):
    """처리권 확보와 함께 생성하는 개별 시도의 결과를 보존한다.

    재시도마다 새 UUID를 만들고 notification의 현재 attempt_id와 대조한다.
    전송 후에는 안내와 시도 결과를 같은 transaction에서 갱신한다.
    """

    id = models.UUIDField(
        "전송 시도 식별자",
        primary_key=True,
        default=uuid7,
        editable=False,
        help_text="처리권 확보 시 생성하는 UUIDv7입니다. 하나의 전송 시도와 그 결과를 연결합니다.",
    )
    notification = models.ForeignKey(
        EducationApplicationReminderEmail,
        verbose_name="상담 안내 이메일",
        on_delete=models.CASCADE,
        related_name="attempts",
        help_text="이 시도가 속한 안내입니다. 재시도 이력도 같은 안내에 연결합니다.",
    )
    started_at = models.DateTimeField(
        "시도 시작 일시",
        default=timezone.now,
        help_text="외부 전송 전에 처리권과 시도 기록을 생성한 시각입니다.",
    )
    finished_at = models.DateTimeField(
        "시도 결과 기록 일시",
        null=True,
        blank=True,
        help_text="결과 또는 중단 복구를 기록한 시각입니다. 처리 중이면 비어 있습니다.",
    )
    state = models.CharField(
        "시도 처리 상태",
        max_length=20,
        choices=EducationApplicationReminderEmail.State,
        default=EducationApplicationReminderEmail.State.SENDING,
        help_text="개별 시도의 처리 결과입니다. unknown은 실제 접수 여부를 확정할 수 없다는 뜻입니다.",
    )
    ses_message_id = models.CharField(
        "SES 메시지 식별자",
        max_length=255,
        blank=True,
        default="",
        help_text="이 시도의 SES 접수 성공 응답에서 확인한 MessageId입니다. 모의 처리에는 없습니다.",
    )
    error_code = models.CharField(
        "안전한 오류 코드",
        max_length=64,
        blank=True,
        default="",
        help_text="이 시도의 분류된 오류 코드입니다. 개인정보나 외부 예외 원문은 저장하지 않습니다.",
    )

    class Meta:
        verbose_name = "메일 전송 시도"
        verbose_name_plural = "메일 전송 시도"


class MailSendBudget(models.Model):
    """여러 worker가 짧은 row lock으로 공유하는 SES 전송 허용 시각이다."""

    id = models.PositiveSmallIntegerField(
        "공유 예산 식별자",
        primary_key=True,
        default=1,
        help_text="항상 1인 단일 공유 예산입니다. 이 DB를 사용하는 worker가 같은 SES 속도 한도를 공유합니다.",
    )
    next_allowed_at = models.DateTimeField(
        "다음 전송 허용 일시",
        default=timezone.now,
        help_text="공유 속도 한도로 예약한 다음 전송 가능 시각입니다. 일일 잔여 발송량은 나타내지 않습니다.",
    )

    class Meta:
        verbose_name = "메일 공유 전송 예산"
        verbose_name_plural = "메일 공유 전송 예산"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="mail_budget_singleton"
            )
        ]
