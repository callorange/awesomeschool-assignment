from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from education.models import Education


class EducationPageTests(TestCase):
    """실제 DB와 임시 미디어로 공개 페이지의 서버 렌더링 계약을 검증한다.

    CSS 적용과 반응형 배치는 별도의 실제 브라우저 검증 범위다.
    """

    def setUp(self):
        self.media = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=self.media))
        call_command("seed_educations", stdout=StringIO())

    def test_landing_has_ordered_cards_and_detail_links(self):
        response = self.client.get(reverse("education:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "education/landing.html")
        self.assertEqual(
            list(response.context["educations"].values_list("slug", flat=True)),
            ["prompt-hero", "emotion-hero", "relationship-hero"],
        )
        self.assertContains(response, "<article", count=3)
        for education in Education.objects.all():
            self.assertContains(response, education.title)
            self.assertContains(response, education.summary)
            self.assertContains(
                response, reverse("education:detail", args=[education.slug])
            )
            self.assertContains(response, education.image.url)

    def test_empty_landing_does_not_link_to_missing_education(self):
        Education.objects.all().delete()
        response = self.client.get(reverse("education:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "교육을 준비하고 있습니다")
        self.assertNotContains(response, "/educations/")

    def test_details_show_all_curriculum_variants_in_period_order(self):
        for education in Education.objects.all():
            with self.subTest(slug=education.slug):
                response = self.client.get(
                    reverse("education:detail", args=[education.slug])
                )
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "education/detail.html")
                self.assertContains(response, education.source_url)
                self.assertContains(response, education.image.url)
                for text in education.goals + education.audiences:
                    self.assertContains(response, text)
                html = response.content.decode()
                for course in education.curriculum:
                    section = html.split(f'id="course-{course["periods"]}"', 1)[
                        1
                    ].split("</section>", 1)[0]
                    position = -1
                    for lesson in course["lessons"]:
                        next_position = section.find(f"{lesson['period']}교시")
                        self.assertGreater(next_position, position)
                        position = next_position
                        self.assertContains(response, lesson["topic"])
                        self.assertContains(response, lesson["description"])

    def test_unknown_education_is_404_and_post_is_not_allowed(self):
        self.assertEqual(self.client.get("/educations/missing/").status_code, 404)
        self.assertEqual(self.client.post("/").status_code, 405)

    def test_content_is_escaped(self):
        Education.objects.filter(slug="prompt-hero").update(
            summary="<script>alert('x')</script>"
        )
        for path in ("/", "/educations/prompt-hero/"):
            response = self.client.get(path)
            self.assertNotContains(response, "<script>")
            self.assertContains(response, "&lt;script&gt;")

    def test_same_templates_use_cloudfront_in_production(self):
        """운영 저장소 URL 렌더링을 검사하며 실제 S3·CloudFront에는 연결하지 않는다."""
        storages = {
            "default": {
                "BACKEND": "storages.backends.s3.S3Storage",
                "OPTIONS": {
                    "bucket_name": "example-education",
                    "custom_domain": "cdn.example.com",
                    "location": "media",
                    "querystring_auth": False,
                    "cloudfront_signer": None,
                },
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
        with override_settings(STORAGES=storages):
            for path in ("/", "/educations/prompt-hero/"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, "https://cdn.example.com/media/education/presets/"
                )
