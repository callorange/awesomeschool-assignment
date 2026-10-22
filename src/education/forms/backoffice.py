"""백오피스의 날짜 입력과 부모 신청에 고정된 상담 추가 폼이다."""

from django import forms

from ..models import ConsultationRecord
from .application import EducationApplicationForm
from .consultation import ConsultationForm


class BackofficeApplicationForm(EducationApplicationForm):
    """공통 신청 변경 검증을 유지하며 날짜·일시를 브라우저 기본 입력으로 표시한다.

    다음 연락 일시는 Django의 현재 시간대인 한국 시각으로 입력·해석한다.
    폼의 save() 대신 기존 저장 서비스를 호출해 안내·이력을 함께 갱신해야 한다.
    """

    class Meta(EducationApplicationForm.Meta):
        widgets = {
            "contact_date": forms.DateInput(attrs={"type": "date"}),
            "cancellation_reason": forms.Textarea(attrs={"rows": 3}),
            "next_contact_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
        }


class BackofficeConsultationForm(ConsultationForm):
    """부모 신청을 서버 인스턴스로 고정하고 상담 조회 권한에 따라 정정을 제한한다.

    이 폼은 부모 연결과 입력만 검증한다. 작성자·당시 일정은 view가 지정하고
    신청 정정과 함께 저장할 때는 호출자가 동일한 transaction으로 묶어야 한다.
    """

    class Meta(ConsultationForm.Meta):
        fields = ("result", "content", "corrects")
        widgets = {"content": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, application, can_view, **kwargs):
        """현재 신청의 원기록만 선택하게 하며 HTML 필수 검증은 사용하지 않는다.

        상담 추가를 선택한 경우의 필수 검증은 서버의 bound 폼이 수행하므로
        JavaScript가 없거나 상담을 선택하지 않아도 신청만 저장할 수 있다.

        Args:
            application: URL과 접근 권한을 확인한 부모 신청 인스턴스.
            can_view: 서버가 확인한 상담 조회 권한. 없으면 정정 선택지를 제거한다.
        """
        # 선택하지 않은 상담의 HTML required가 신청만 저장하는 동작을 막지 않게 한다.
        kwargs["use_required_attribute"] = False
        super().__init__(*args, **kwargs)
        self.instance.application = application
        self.can_view = can_view
        self.fields["result"].initial = ""
        self.fields["corrects"].queryset = application.consultations.all()
        if not can_view:
            self.fields.pop("corrects")
            self.fields["result"].choices = [
                choice
                for choice in self.fields["result"].choices
                if choice[0] != ConsultationRecord.Result.CORRECTION
            ]

    def clean(self):
        """조회 권한 없이 정정 결과나 원기록 ID를 직접 제출하는 우회를 거부한다."""
        values = super().clean()
        if not self.can_view and (
            values.get("result") == ConsultationRecord.Result.CORRECTION
            or self.data.get(self.add_prefix("corrects"))
        ):
            raise forms.ValidationError(
                "기존 상담을 정정하려면 상담 조회 권한이 필요합니다."
            )
        return values
