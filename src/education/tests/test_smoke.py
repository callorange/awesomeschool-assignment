from django.db import connection
from django.test import TestCase
from django.urls import reverse


class ProjectSmokeTests(TestCase):
    """Django가 격리한 PostgreSQL 테스트 DB와 기본 관리자 화면을 검증한다."""

    def test_postgresql_connection(self):
        """PostgreSQL 테스트 DB에 쿼리를 실행해 연결과 응답을 확인한다."""
        self.assertEqual(connection.vendor, "postgresql")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone(), (1,))

    def test_admin_login_is_available(self):
        """비로그인 요청에 관리자 로그인 폼이 렌더링되는지 확인한다.

        검증 범위는 HTML 렌더링이며 CSS 제공은 실제 개발 서버에서 별도로 확인한다.
        """
        response = self.client.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/login.html")
        self.assertContains(response, 'name="username"')
