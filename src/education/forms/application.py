"""신청 정정 입력에 공통 변경 검증을 적용한다."""

from django import forms

from ..models import EducationApplication, EducationApplicationReminderEmail
from ..services.applications import EDITABLE_FIELDS, validate_change


class EducationApplicationForm(forms.ModelForm):
    """안내가 연결된 기존 신청의 편집 전용 폼이다.

    clean()은 공통 검증으로 cleaned_data의 일정·취소 사유도 정리한다. 발송과의
    경합 제어는 admin의 폼 조회 전 잠금과 저장 서비스의 재검증에서 보장한다.
    """

    class Meta:
        model = EducationApplication
        fields = EDITABLE_FIELDS

    def clean(self):
        values = super().clean()
        if not self.errors:
            notification = EducationApplicationReminderEmail.objects.get(
                application=self.instance
            )
            validate_change(self.instance, values, notification)
        return values
