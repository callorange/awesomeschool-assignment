import json
from copy import deepcopy

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from education.models import Education


class EducationTests(TestCase):
    """실제 PostgreSQL에서 소개 데이터 보존과 slug 고유성을 검증한다."""

    def test_media_id_is_unique_and_excluded_from_edit_forms(self):
        education = Education.objects.create(slug="media-id")
        identifier = education.media_id
        education.refresh_from_db()
        self.assertEqual(education.media_id, identifier)
        self.assertEqual(identifier.version, 7)
        self.assertFalse(Education._meta.get_field("media_id").editable)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Education.objects.create(
                slug="duplicate-media-id",
                media_id=identifier,
            )

    def test_operation_defaults_and_persistence(self):
        education = Education.objects.create(slug="operations")
        education.refresh_from_db()
        self.assertEqual(
            education.operation_type, Education.OperationType.INSTRUCTOR_LED
        )
        self.assertEqual(education.operation_note, "")
        self.assertIs(education.is_accepting_inquiries, True)
        education.operation_type = Education.OperationType.COURSEWARE
        education.operation_note = "기기와 학습 환경은 상담 시 안내합니다."
        education.is_accepting_inquiries = False
        education.save()
        education.refresh_from_db()
        self.assertEqual(education.operation_type, "courseware")
        self.assertEqual(
            education.operation_note, "기기와 학습 환경은 상담 시 안내합니다."
        )
        self.assertIs(education.is_accepting_inquiries, False)

    def test_persistence_and_unique_slug(self):
        education = Education.objects.create(
            slug="prompt-hero",
            title="프롬프트 히어로",
            summary="소개",
            image="education/prompt.png",
            image_alt="교육 캐릭터",
            goals=["AI 활용"],
            audiences=["학생"],
            curriculum=[{"periods": 2}],
        )
        education.refresh_from_db()
        self.assertEqual(education.image.name, "education/prompt.png")
        self.assertEqual(education.goals, ["AI 활용"])
        self.assertEqual(education.curriculum, [{"periods": 2}])
        self.assertEqual(str(education), "프롬프트 히어로")
        # 의도한 무결성 오류가 테스트의 바깥 transaction을 무효화하지 않게 격리한다.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Education.objects.create(slug="prompt-hero")


class EducationValidationTests(SimpleTestCase):
    """DB 쓰기 없이 full_clean()의 필드별 콘텐츠 검증 계약을 확인한다."""

    def setUp(self):
        source = settings.BASE_DIR.parent / "presets/education/education_presets.json"
        self.fields = json.loads(source.read_text(encoding="utf-8"))[0]
        for key in ("source_url", "source_image_url", "collected_on", "editorial_note"):
            self.fields.pop(key, None)

    def test_valid_content_for_both_operation_types(self):
        for operation_type in Education.OperationType.values:
            with self.subTest(operation_type=operation_type):
                education = Education(**self.fields)
                education.operation_type = operation_type
                education.operation_note = ""
                before = deepcopy(education.curriculum)
                education.full_clean(validate_unique=False)
                self.assertEqual(education.curriculum, before)
                self.assertEqual(education.operation_type, operation_type)

    def test_invalid_operation_type(self):
        education = Education(**self.fields)
        education.operation_type = "unknown"
        with self.assertRaises(ValidationError) as error:
            education.full_clean(validate_unique=False)
        self.assertEqual(set(error.exception.message_dict), {"operation_type"})

    def test_invalid_text_lists(self):
        for field in ("goals", "audiences"):
            for value in ([], {}, "text", None, [" "], [1], [True]):
                with self.subTest(field=field, value=value):
                    education = Education(**self.fields)
                    setattr(education, field, value)
                    with self.assertRaises(ValidationError) as error:
                        education.full_clean(validate_unique=False)
                    self.assertEqual(set(error.exception.message_dict), {field})

    def test_invalid_curriculum(self):
        course = self.fields["curriculum"][0]
        invalid = [[], {}, None, "text", [None], [{}]]
        for value in (True, 0, -1, "4", [4]):
            invalid.append([dict(course, periods=value)])
        invalid.extend(
            [[course, course], [dict(course, lessons=[])], [dict(course, lessons={})]]
        )
        for value in (None, {}, "lesson"):
            invalid.append([dict(course, lessons=[value] * course["periods"])])
        for key, value in (
            ("period", 9),
            ("period", True),
            ("topic", " "),
            ("activity", 1),
            ("description", None),
        ):
            modified = deepcopy(course)
            modified["lessons"][0][key] = value
            invalid.append([modified])
        modified = deepcopy(course)
        del modified["lessons"][0]["description"]
        invalid.append([modified])
        for curriculum in invalid:
            with self.subTest(curriculum=curriculum):
                education = Education(**self.fields)
                education.curriculum = curriculum
                with self.assertRaises(ValidationError) as error:
                    education.full_clean(validate_unique=False)
                self.assertEqual(set(error.exception.message_dict), {"curriculum"})
