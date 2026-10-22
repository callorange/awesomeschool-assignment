"""상담 추가 폼의 정정 대상은 같은 신청의 기존 기록으로 제한한다."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from ..models import ConsultationRecord


class NewConsultationFormSet(BaseInlineFormSet):
    """추가 전용 inline의 정정 대상은 부모 신청의 기존 기록으로 제한한다."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.fields["corrects"].queryset = self.instance.consultations.all()

    def clean(self):
        super().clean()
        if any(form.instance.pk for form in self.forms):
            raise ValidationError("기존 상담 기록은 수정할 수 없습니다.")


class ConsultationForm(forms.ModelForm):
    """선택한 신청의 기록만 정정 대상으로 제공하고 연결 검증은 모델에서도 수행한다.

    bound 폼은 제출된 신청 ID를 사용하므로 유효성 오류 후에도 대상 목록을 유지한다.
    신청이 선택되지 않았거나 잘못된 ID이면 다른 신청의 기록을 노출하지 않는다.
    """

    class Meta:
        model = ConsultationRecord
        fields = ("application", "result", "content", "corrects")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "corrects" not in self.fields:
            return
        application_id = (
            self.data.get("application")
            if self.is_bound
            else self.initial.get("application")
        )
        # 다른 신청의 기록 내용을 선택 목록에 노출하지 않는다.
        try:
            application_id = int(application_id)
        except ValueError, TypeError:
            application_id = None
        self.fields["corrects"].queryset = ConsultationRecord.objects.filter(
            application_id=application_id
        )
