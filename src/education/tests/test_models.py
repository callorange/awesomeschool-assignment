from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from education.models import Education


class EducationTests(TestCase):
    """실제 PostgreSQL에서 소개 데이터 보존과 slug 고유성을 검증한다."""

    def test_persistence_and_unique_slug(self):
        education = Education.objects.create(
            slug="prompt-hero",
            title="프롬프트 히어로",
            summary="소개",
            image="education/prompt.png",
            image_alt="교육 캐릭터",
            collected_on=date(2026, 10, 21),
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
            Education.objects.create(slug="prompt-hero", collected_on=date.today())
