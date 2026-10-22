"""공개 교육 안내와 상담 접수의 입력·반복 제출·최소 응답 계약을 정의한다."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound

from .models import Education, EducationApplication, EducationApplicationReminderEmail


class SubmissionConflict(APIException):
    status_code = 409
    default_detail = "제출 식별자가 다른 신청 내용에 이미 사용되었습니다."


class EducationSerializer(serializers.ModelSerializer):
    """신청 화면에 필요한 공개 교육 안내와 선택된 Storage의 이미지 URL을 제공한다."""

    image_url = serializers.FileField(source="image", read_only=True)

    class Meta:
        model = Education
        fields = (
            "slug",
            "title",
            "summary",
            "image_url",
            "image_alt",
            "operation_type",
            "operation_note",
            "is_accepting_inquiries",
        )


class EducationApplicationSerializer(serializers.Serializer):
    """입력을 정규화한 뒤 기존 제출을 확인하고 신규 신청·안내만 함께 생성한다.

    저장 후 created로 신규 생성 여부를 제공하며 API가 201/200을 구분한다.
    과거 날짜·교육 접수 상태 검사는 기존 제출 확인 뒤 신규 신청에만 적용한다.
    """

    education_slug = serializers.SlugField(max_length=50)
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=254)
    postal_code = serializers.RegexField(r"^[0-9]{5}$", max_length=5)
    address = serializers.CharField(max_length=255)
    address_detail = serializers.CharField(max_length=255, allow_blank=True, default="")
    contact_date = serializers.DateField(input_formats=["%Y-%m-%d"])
    request_id = serializers.UUIDField()

    def to_internal_value(self, data):
        """DRF가 기본적으로 무시하는 미정의 필드도 오류로 반환해 쓰기 계약을 제한한다."""
        if isinstance(data, dict):
            extra = set(data) - set(self.fields)
            if extra:
                raise serializers.ValidationError(
                    {key: ["허용하지 않는 입력 필드입니다."] for key in sorted(extra)}
                )
        return super().to_internal_value(data)

    def _reuse(self, application, values):
        """정규화한 입력을 snapshot과 비교하고 일치할 때만 기존 접수를 재사용한다.

        Raises:
            SubmissionConflict: 같은 request_id에 다른 입력이 제출된 경우.
        """
        if application.submission_snapshot != {
            field: str(value) for field, value in values.items()
        }:
            raise SubmissionConflict()
        self.created = False
        return application

    def create(self, validated_data):
        """교육 row lock 아래 접수 가능 여부를 검사하고 신청·안내를 함께 저장한다.

        기존 제출 확인은 교육 조회 전후에 수행해 lock 대기 중 commit된 제출도
        재사용한다. request_id 충돌은 내부 savepoint를 rollback한 뒤 비교한다.
        안내 시작은 한국 날짜 09시와 생성 시각 중 늦은 값이다.

        Raises:
            NotFound: 신규 신청의 교육이 없는 경우.
            serializers.ValidationError: 신규 신청의 날짜가 지났거나 접수가 중단된 경우.
            SubmissionConflict: 같은 request_id에 다른 입력이 저장된 경우.
        """
        with transaction.atomic():
            existing = EducationApplication.objects.filter(
                request_id=validated_data["request_id"]
            ).first()
            if existing:
                return self._reuse(existing, validated_data)
            education = (
                Education.objects.select_for_update()
                .filter(slug=validated_data["education_slug"])
                .first()
            )
            # 교육 lock을 기다리는 동안 원래 제출이 commit됐을 수 있다.
            existing = EducationApplication.objects.filter(
                request_id=validated_data["request_id"]
            ).first()
            if existing:
                return self._reuse(existing, validated_data)
            if education is None:
                raise NotFound("교육 정보를 찾을 수 없습니다.")
            if validated_data["contact_date"] < timezone.localdate():
                raise serializers.ValidationError(
                    {"contact_date": ["오늘을 포함한 이후 날짜를 선택해 주세요."]}
                )
            if not education.is_accepting_inquiries:
                raise serializers.ValidationError(
                    {"education_slug": ["현재 상담 접수가 중단된 교육입니다."]}
                )
            try:
                with transaction.atomic():
                    application = EducationApplication.objects.create(
                        **validated_data,
                        education=education,
                        education_title=education.title,
                    )
                    morning = datetime.combine(
                        application.contact_date,
                        time(9),
                        tzinfo=ZoneInfo(settings.TIME_ZONE),
                    )
                    EducationApplicationReminderEmail.objects.create(
                        application=application,
                        due_at=max(morning, application.created_at),
                        mode=settings.NOTIFICATION_MODE,
                    )
            except IntegrityError:
                existing = EducationApplication.objects.filter(
                    request_id=validated_data["request_id"]
                ).first()
                if existing is None:
                    raise
                return self._reuse(existing, validated_data)
        self.created = True
        return application
