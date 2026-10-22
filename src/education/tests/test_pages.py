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
                self.assertNotContains(response, "교육 정보 출처")
                self.assertNotContains(response, "수집일:")
                self.assertNotContains(response, "히어로스쿨에서 원문 보기")
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

    def test_operation_information_is_escaped_and_links_to_application(self):
        education = Education.objects.get(slug="prompt-hero")
        note = "<script>공개 안내</script>\n준비사항을 확인하세요."
        for operation_type, label in Education.OperationType.choices:
            with self.subTest(operation_type=operation_type):
                education.operation_type = operation_type
                education.operation_note = note
                education.save()
                response = self.client.get(
                    reverse("education:detail", args=[education.slug])
                )
                self.assertContains(response, label)
                self.assertContains(response, "상담 접수 가능")
                self.assertContains(
                    response, "수강이나 교육 일정의 확정을 의미하지 않습니다"
                )
                self.assertContains(response, "&lt;script&gt;공개 안내&lt;/script&gt;")
                self.assertNotContains(response, "<script>")
                self.assertContains(
                    response, reverse("education:application", args=[education.slug])
                )
                self.assertNotContains(response, "<form")

    def test_inactive_education_remains_public_and_empty_note_is_omitted(self):
        Education.objects.filter(slug="prompt-hero").update(
            operation_note="", is_accepting_inquiries=False
        )
        landing = self.client.get(reverse("education:landing"))
        detail_url = reverse("education:detail", args=["prompt-hero"])
        self.assertContains(landing, detail_url)
        response = self.client.get(detail_url)
        self.assertContains(response, "상담 접수 중단")
        self.assertNotContains(response, "상담 접수 가능")
        self.assertNotContains(response, "whitespace-pre-line")
        self.assertNotContains(response, "/apply/")
        self.assertContains(response, 'id="curriculum"')

    def test_content_is_escaped(self):
        Education.objects.filter(slug="prompt-hero").update(
            summary="<script>alert('x')</script>"
        )
        for path in ("/", "/educations/prompt-hero/"):
            response = self.client.get(path)
            self.assertNotContains(response, "<script>")
            self.assertContains(response, "&lt;script&gt;")

    def test_application_shell_has_csrf_api_links_and_accessible_fields(self):
        response = self.client.get("/educations/prompt-hero/apply/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "education/application.html")
        self.assertIn("csrftoken", response.cookies)
        self.assertContains(response, "/static/js/application.js", count=1)
        for path in ("/", "/educations/prompt-hero/"):
            self.assertNotContains(self.client.get(path), "/static/js/application.js")
        for text in (
            'data-education-url="/api/educations/prompt-hero/"',
            'data-submit-url="/api/applications/"',
            'name="csrfmiddlewaretoken"',
            'autocomplete="email"',
            'type="date"',
            'aria-live="polite"',
            "주소 검색",
            "직접 입력",
        ):
            self.assertContains(response, text)
        for name in (
            "name",
            "email",
            "postal_code",
            "address",
            "address_detail",
            "contact_date",
        ):
            self.assertContains(response, f'for="{name}"')
            self.assertContains(response, f'id="{name}-error"')
        self.assertEqual(self.client.get("/educations/missing/apply/").status_code, 404)
        self.assertEqual(
            self.client.post("/educations/prompt-hero/apply/").status_code, 405
        )
        Education.objects.filter(slug="prompt-hero").update(
            is_accepting_inquiries=False
        )
        response = self.client.get("/educations/prompt-hero/apply/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="application-fields" disabled')

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
                    response,
                    "https://cdn.example.com/media/"
                    + Education.objects.get(slug="prompt-hero").image.name,
                )

    def test_legacy_image_url_still_renders(self):
        key = "education/presets/legacy.png"
        Education.objects.filter(slug="prompt-hero").update(image=key)
        for path in ("/", "/educations/prompt-hero/"):
            self.assertContains(self.client.get(path), "/media/" + key)
