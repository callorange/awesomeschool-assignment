from uuid import uuid7

from django.db import models

from .media import education_image_upload_to
from .validators import validate_curriculum, validate_text_list


class Education(models.Model):
    """공개 교육 소개와 저장소에 독립적인 대표 이미지 참조를 보관한다.

    goals와 audiences는 문자열 목록이다. curriculum은 periods(시수)와
    lessons(교시 목록)으로 구성하며, 각 교시는 period·topic·activity·description을
    가진다. full_clean()과 이를 호출하는 프리셋 명령이 JSON 구조를 검증한다.
    save()·QuerySet.update()는 입력 검증을 자동 실행하지 않는다.
    운영 방식과 상담 접수 상태는 향후 신청 입력에서 사용할 값이며,
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
