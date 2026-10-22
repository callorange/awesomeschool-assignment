"""관리자 일반 입력의 JSON 변환·검증과 오류 시 입력 보존을 확인한다."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from education.forms.education import CurriculumField, CurriculumWidget, TextListField
from education.validators import validate_curriculum, validate_text_list


class EducationContentFormTests(SimpleTestCase):
    def payload(self):
        return {
            "curriculum-TOTAL_FORMS": "2",
            "curriculum-INITIAL_FORMS": "1",
            "curriculum-0-periods": "1",
            "curriculum-0-period": "1",
            "curriculum-0-topic": "기존 주제",
            "curriculum-0-activity": "기존 활동",
            "curriculum-0-description": "기존 설명",
            "curriculum-1-periods": "1",
            "curriculum-1-period": "1",
            "curriculum-1-topic": "새 주제",
            "curriculum-1-activity": "새 활동",
            "curriculum-1-description": "새 설명",
        }

    def test_text_list_accepts_lines_and_displays_plain_text(self):
        field = TextListField(validators=[validate_text_list])
        self.assertEqual(
            field.clean(" 목표 하나 \r\n\n목표 둘 "), ["목표 하나", "목표 둘"]
        )
        self.assertEqual(
            field.prepare_value(["목표 하나", "목표 둘"]), "목표 하나\n목표 둘"
        )
        with self.assertRaises(ValidationError):
            field.clean(" \n ")

    def test_lesson_add_delete_and_structure_validation(self):
        data = self.payload()
        data["curriculum-0-DELETE"] = "on"
        widget = CurriculumWidget()
        field = CurriculumField(validators=[validate_curriculum])
        value = field.clean(widget.value_from_datadict(data, {}, "curriculum"))
        self.assertEqual(
            value,
            [
                {
                    "periods": 1,
                    "lessons": [
                        {
                            "period": 1,
                            "topic": "새 주제",
                            "activity": "새 활동",
                            "description": "새 설명",
                        }
                    ],
                }
            ],
        )
        data["curriculum-1-periods"] = "2"
        with self.assertRaisesMessage(ValidationError, "시수와 교시 수가 다릅니다"):
            field.clean(widget.value_from_datadict(data, {}, "curriculum"))

    def test_errors_keep_rows_escape_values_and_require_management_data(self):
        data = self.payload()
        data["curriculum-0-topic"] = '<script>alert("test")</script>'
        data["curriculum-1-activity"] = ""
        widget = CurriculumWidget()
        value = widget.value_from_datadict(data, {}, "curriculum")
        with self.assertRaises(ValidationError):
            CurriculumField().clean(value)
        rendered = widget.render("curriculum", value)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>alert", rendered)
        self.assertIn("curriculum-1-activity", rendered)
        with self.assertRaises(ValidationError):
            CurriculumField().clean(widget.value_from_datadict({}, {}, "curriculum"))
