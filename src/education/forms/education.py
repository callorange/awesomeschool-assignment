"""교육 콘텐츠는 일반 입력 폼으로 편집하고 기존 JSON 저장 계약으로 변환한다."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory
from django.template.loader import get_template

from ..models import Education
from ..validators import validate_curriculum, validate_text_list


class TextListField(forms.CharField):
    """줄 단위 입력을 문자열 목록으로 바꾸고 기존 목록은 텍스트로 표시한다.

    각 줄의 양끝 공백과 빈 줄은 제거하며 남은 항목의 순서와 중복은 유지한다.
    """

    widget = forms.Textarea

    def prepare_value(self, value):
        if isinstance(value, list):
            return "\n".join(value)
        return value

    def to_python(self, value):
        return [
            line.strip()
            for line in super().to_python(value).splitlines()
            if line.strip()
        ]


class LessonForm(forms.Form):
    periods = forms.IntegerField(label="총 차시 수", min_value=1)
    period = forms.IntegerField(label="교시", min_value=1)
    topic = forms.CharField(label="주제")
    activity = forms.CharField(label="활동")
    description = forms.CharField(
        label="활동 설명", widget=forms.Textarea(attrs={"rows": 2, "cols": 50})
    )


LessonFormSet = formset_factory(LessonForm, extra=1, can_delete=True)


class CurriculumWidget(forms.Widget):
    """기존 JSON과 오류가 있는 bound formset을 같은 교시 폼으로 표시한다.

    초기 JSON은 교시 행으로 펼치고 제출 시에는 필드명을 prefix로 한 formset을
    반환한다. bound formset 자체를 다시 렌더링해 오류·삭제 선택·추가 행을 보존한다.
    """

    template_name = "education/widgets/curriculum.html"

    class Media:
        js = ("js/education-admin.js",)

    def render(self, name, value, attrs=None, renderer=None):
        # 프로젝트 templates/의 위젯을 사용하므로 form renderer 대신 loader를 쓴다.
        return get_template(self.template_name).render(
            self.get_context(name, value, attrs)
        )

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if not isinstance(value, BaseFormSet):
            initial = [
                {"periods": course["periods"], **lesson}
                for course in value or []
                for lesson in course["lessons"]
            ]
            value = LessonFormSet(initial=initial, prefix=name)
        context["widget"]["formset"] = value
        return context

    def value_from_datadict(self, data, files, name):
        return LessonFormSet(data=data, files=files, prefix=name)

    def value_omitted_from_data(self, data, files, name):
        # 단일 name 입력이 없으므로 formset 관리 필드로 제출 여부를 판별한다.
        return f"{name}-TOTAL_FORMS" not in data


class CurriculumField(forms.Field):
    """유효한 교시를 총 차시 수별로 묶고 입력 순서는 공통 validator로 검사한다.

    입력은 위젯이 만든 bound formset이다. 빈 추가 행과 삭제한 행은 저장하지 않는다.
    교시 번호를 자동 재정렬하지 않으므로 순서·교시 수 오류를 관리자가 확인할 수 있다.
    """

    widget = CurriculumWidget

    def to_python(self, value):
        if not value.is_valid():
            raise ValidationError("각 교시의 입력 오류를 확인해 주세요.")
        courses = {}
        for row in value.cleaned_data:
            if not row or row.get("DELETE"):
                continue
            lessons = courses.setdefault(row["periods"], [])
            lessons.append(
                {
                    key: row[key]
                    for key in ("period", "topic", "activity", "description")
                }
            )
        return [
            {"periods": periods, "lessons": lessons}
            for periods, lessons in courses.items()
        ]


class EducationForm(forms.ModelForm):
    goals = TextListField(
        label="교육 목표",
        validators=[validate_text_list],
        help_text="한 줄에 목표 하나씩 입력합니다.",
    )
    audiences = TextListField(
        label="추천 대상",
        validators=[validate_text_list],
        help_text="한 줄에 대상 하나씩 입력합니다.",
    )
    curriculum = CurriculumField(
        label="시수별 커리큘럼",
        validators=[validate_curriculum],
        help_text="같은 총 차시 수의 교시를 1부터 순서대로 입력합니다. 교시 수는 총 차시 수와 같아야 합니다.",
    )

    class Meta:
        model = Education
        fields = "__all__"
