"""실제 PostgreSQL에서 백오피스 권한·입력·원자적 저장·부분 조회를 검증한다."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from education.models import ConsultationRecord, Education, EducationApplication
from education.services.applications import EDITABLE_FIELDS
from education.tests.test_notifications import notification


class BackofficeTests(TestCase):
    """권한별 HTTP 응답과 실제 DB 상태를 확인하며 외부 발송은 실행하지 않는다."""

    @classmethod
    def setUpTestData(cls):
        cls.editor = cls.user(
            "editor",
            "view_educationapplication",
            "change_educationapplication",
            "view_consultationrecord",
            "add_consultationrecord",
            "view_educationapplicationreminderemail",
        )
        cls.reader = cls.user("reader", "view_educationapplication")
        cls.writer = cls.user(
            "writer", "view_educationapplication", "add_consultationrecord"
        )
        cls.changer = cls.user(
            "changer", "view_educationapplication", "change_educationapplication"
        )
        cls.staff = cls.user("staff")
        cls.outsider = get_user_model().objects.create_user(
            "outsider", password="test-password"
        )
        cls.inactive = cls.user("inactive", "view_educationapplication")
        cls.inactive.is_active = False
        cls.inactive.save()
        cls.superuser = get_user_model().objects.create_superuser(
            "super", password="test-password"
        )

    @classmethod
    def user(cls, name, *permissions):
        """education 앱의 지정 모델 권한만 가진 활성 staff 테스트 계정을 만든다."""
        user = get_user_model().objects.create_user(
            name, password="test-password", is_staff=True
        )
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="education",
                codename__in=permissions,
            )
        )
        return user

    def setUp(self):
        self.row = notification()
        self.application = self.row.application
        self.detail = reverse(
            "backoffice:application-detail", args=[self.application.pk]
        )
        self.listing = reverse("backoffice:application-list")
        self.email = reverse("backoffice:email-status", args=[self.application.pk])
        self.client.force_login(self.editor)

    def payload(self, **changes):
        """현재 신청값을 HTML 폼 prefix로 구성하고 명시한 POST 항목만 덮어쓴다."""
        data = {
            f"application-{field}": getattr(self.application, field) or ""
            for field in EDITABLE_FIELDS
        }
        data["action"] = "save_application"
        data.update(changes)
        return data

    def consultation(self, **changes):
        """통합 저장에서 상담 추가 선택과 필수 입력을 포함하는 POST 조각을 만든다."""
        return {
            "include_consultation": "on",
            "consultation-result": "unreachable",
            "consultation-content": "상담 내용",
            **changes,
        }

    def test_login_roles_safe_next_and_shared_logout(self):
        self.client.logout()
        response = self.client.get(self.detail)
        self.assertRedirects(
            response, reverse("backoffice:login") + "?next=" + self.detail
        )
        for username in ("outsider", "inactive", "not-found"):
            with self.subTest(username=username):
                response = self.client.post(
                    reverse("backoffice:login"),
                    {
                        "username": username,
                        "password": "test-password",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(
            reverse("backoffice:login"),
            {
                "username": "editor",
                "password": "test-password",
                "next": self.detail,
            },
        )
        self.assertRedirects(response, self.detail)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("backoffice:logout")).status_code, 405)
        self.assertRedirects(
            self.client.post(reverse("backoffice:logout")), reverse("backoffice:login")
        )
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
        response = self.client.post(
            reverse("backoffice:login"),
            {
                "username": "editor",
                "password": "test-password",
                "next": "https://evil.example/",
            },
        )
        self.assertRedirects(response, self.listing)
        self.client.post(reverse("admin:logout"))
        self.assertEqual(self.client.get(self.detail).status_code, 302)

    def test_staff_and_model_permissions_protect_all_responses(self):
        for user in (self.staff, self.outsider):
            self.client.force_login(user)
            for url in (self.listing, self.detail, self.email):
                with self.subTest(user=user.username, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertNotContains(
                        response, self.application.email, status_code=403
                    )
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(self.detail).status_code, 200)

    def test_reader_only_sees_authorized_data_and_cannot_write(self):
        ConsultationRecord.objects.create(
            application=self.application,
            author=self.editor,
            result="consulted",
            content="秘密相談",
        )
        self.row.error_code = "InternalCode"
        self.row.save()
        self.client.force_login(self.reader)
        page = self.client.get(self.detail)
        self.assertContains(page, self.application.email)
        for content in (
            "秘密相談",
            "InternalCode",
            "変更事項",
            'name="action"',
            "backoffice-detail.js",
        ):
            self.assertNotContains(page, content)
        self.assertIn("no-store", page.headers["Cache-Control"])
        self.assertIn("private", page.headers["Cache-Control"])
        self.assertEqual(self.client.post(self.detail, self.payload()).status_code, 403)
        self.assertEqual(
            self.client.post(self.detail, {"action": "add_consultation"}).status_code,
            403,
        )
        self.assertEqual(self.client.get(self.email).status_code, 403)

    def test_listing_filters_pagination_and_empty_results(self):
        for number in range(22):
            row = notification()
            row.application.name = f"조회대상 {number}"
            row.application.save()
        page = self.client.get(self.listing, {"q": "조회대상", "page": 2})
        self.assertEqual(len(page.context["page_obj"]), 2)
        self.assertContains(page, "q=%EC%A1%B0%ED%9A%8C%EB%8C%80%EC%83%81")
        for value in ("invalid", "999"):
            self.assertEqual(
                self.client.get(self.listing, {"page": value}).status_code, 200
            )
        self.assertContains(
            self.client.get(self.listing, {"q": "no-match"}),
            "조건에 맞는 신청이 없습니다",
        )
        self.assertEqual(
            self.client.get(
                self.listing,
                {
                    "q": self.application.email,
                    "status": "received",
                    "education_title": self.application.education_title,
                },
            )
            .context["page_obj"]
            .paginator.count,
            23,
        )

    def test_follow_up_filters_use_korean_dates_and_deleted_education_snapshot(self):
        now = timezone.now()
        for scheduled in (now - timedelta(minutes=1), now + timedelta(days=2), None):
            row = notification()
            row.application.status = "follow_up"
            row.application.next_contact_at = scheduled
            row.application.save()
        for category in ("today", "overdue", "undated"):
            result = self.client.get(self.listing, {"follow_up": category})
            self.assertEqual(result.context["page_obj"].paginator.count, 1)
        education = Education.objects.create(
            title="원본 교육", slug="deleted-course", summary="소개"
        )
        self.application.education = education
        self.application.save()
        education.delete()
        self.assertContains(
            self.client.get(self.detail), "교육 &lt;b&gt;제목&lt;/b&gt;"
        )
        page = self.client.get(
            self.listing, {"education_title": self.application.education_title}
        )
        self.assertEqual(page.context["page_obj"].paginator.count, 4)

    def test_application_only_save_keeps_snapshot_history_and_ignores_unselected_consultation(
        self,
    ):
        snapshot = self.application.submission_snapshot.copy()
        response = self.client.post(
            self.detail,
            self.payload(
                **{
                    "application-name": "정정 이름",
                    "consultation-content": "선택 안 한 상담",
                    "application-submission_snapshot": "{}",
                    "application-education_title": "변조",
                }
            ),
        )
        self.assertRedirects(response, self.detail)
        self.application.refresh_from_db()
        self.assertEqual(self.application.name, "정정 이름")
        self.assertEqual(self.application.submission_snapshot, snapshot)
        self.assertEqual(
            self.application.history.latest().history_user_id, self.editor.pk
        )
        self.assertEqual(self.application.consultations.count(), 0)
        self.assertNotEqual(self.application.education_title, "변조")

    def test_combined_save_records_server_author_and_updated_schedule(self):
        scheduled = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        response = self.client.post(
            self.detail,
            self.payload(
                **self.consultation(
                    **{
                        "application-status": "follow_up",
                        "application-next_contact_at": timezone.localtime(
                            scheduled
                        ).strftime("%Y-%m-%dT%H:%M"),
                        "consultation-author": self.outsider.pk,
                        "consultation-application": 999999,
                    }
                )
            ),
        )
        self.assertRedirects(response, self.detail)
        record = self.application.consultations.get()
        self.assertEqual(record.author_id, self.editor.pk)
        self.assertEqual(record.next_contact_at, scheduled)
        self.client.get(self.detail)
        self.assertEqual(self.application.consultations.count(), 1)

    def test_selected_empty_or_partial_consultation_preserves_all_input_without_save(
        self,
    ):
        for fields in ({}, {"consultation-result": "consulted"}):
            response = self.client.post(
                self.detail,
                self.payload(
                    **{
                        "application-name": "未保存",
                        "include_consultation": "on",
                        **fields,
                    }
                ),
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "未保存")
            self.assertTrue(response.context["include_consultation"])
            self.assertTrue(response.context["consultation_form"].errors)
            self.application.refresh_from_db()
            self.assertNotEqual(self.application.name, "未保存")
            self.assertEqual(self.application.consultations.count(), 0)

    def test_consultation_only_permission_and_correction_boundary(self):
        original = ConsultationRecord.objects.create(
            application=self.application,
            author=self.editor,
            result="consulted",
            content="원기록",
        )
        self.client.force_login(self.writer)
        response = self.client.get(self.detail)
        self.assertNotContains(response, "원기록")
        self.assertNotContains(response, 'name="consultation-corrects"')
        for data in (
            {"action": "save_application"},
            {"action": "add_consultation"},
            {
                "action": "add_consultation",
                **self.consultation(
                    **{
                        "consultation-result": "correction",
                        "consultation-corrects": original.pk,
                    }
                ),
            },
        ):
            response = self.client.post(self.detail, data)
            self.assertIn(response.status_code, (200, 403))
            self.assertEqual(self.application.consultations.count(), 1)
        response = self.client.post(
            self.detail,
            {
                "action": "add_consultation",
                "application-name": "변조",
                **self.consultation(),
            },
        )
        self.assertRedirects(response, self.detail)
        self.application.refresh_from_db()
        self.assertNotEqual(self.application.name, "변조")
        self.assertEqual(
            self.application.consultations.latest("pk").author_id, self.writer.pk
        )

    def test_correction_is_append_only_and_rejects_other_application(self):
        original = ConsultationRecord.objects.create(
            application=self.application,
            author=self.editor,
            result="consulted",
            content="원문",
        )
        other = notification().application
        foreign = ConsultationRecord.objects.create(
            application=other,
            author=self.editor,
            result="consulted",
            content="다른 신청 비밀",
        )
        response = self.client.post(
            self.detail,
            self.payload(
                **self.consultation(
                    **{
                        "consultation-result": "correction",
                        "consultation-corrects": foreign.pk,
                    }
                )
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["consultation_form"].errors)
        self.assertNotContains(response, "다른 신청 비밀")
        response = self.client.post(
            self.detail,
            self.payload(
                **self.consultation(
                    **{
                        "consultation-result": "correction",
                        "consultation-corrects": original.pk,
                    }
                )
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.application.consultations.count(), 2)
        original.refresh_from_db()
        self.assertEqual(original.content, "원문")

    def test_application_validation_and_notification_adjustment(self):
        for fields in (
            {"application-email": "bad"},
            {"application-postal_code": "abc"},
            {"application-status": "cancelled"},
            {
                "application-next_contact_at": timezone.now() - timedelta(days=1),
                "application-status": "follow_up",
            },
        ):
            response = self.client.post(self.detail, self.payload(**fields))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["application_form"].errors)
        future = timezone.localdate() + timedelta(days=2)
        self.assertEqual(
            self.client.post(
                self.detail, self.payload(**{"application-contact_date": future})
            ).status_code,
            302,
        )
        self.row.refresh_from_db()
        self.assertEqual(timezone.localtime(self.row.due_at).date(), future)
        self.application.refresh_from_db()
        response = self.client.post(
            self.detail,
            self.payload(
                **{
                    "application-status": "cancelled",
                    "application-cancellation_reason": "취소 합의",
                }
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.state, "suppressed")

    def test_sending_blocks_identity_and_terminal_changes(self):
        self.row.state = "sending"
        self.row.save()
        for fields in (
            {"application-name": "변경"},
            {"application-email": "new@example.com"},
            {"application-contact_date": timezone.localdate() + timedelta(days=1)},
            {"application-status": "completed"},
        ):
            response = self.client.post(self.detail, self.payload(**fields))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["application_form"].errors)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "received")

    def test_save_exceptions_roll_back_application_history_and_notification(self):
        before = self.application.history.count()
        for target in (
            "education.models.ConsultationRecord.save",
            "simple_history.models.HistoricalRecords.create_historical_record",
        ):
            with (
                self.subTest(target=target),
                patch(target, side_effect=ValidationError("저장 실패")),
            ):
                response = self.client.post(
                    self.detail,
                    self.payload(
                        **self.consultation(
                            **{
                                "application-name": "실패 이름",
                                "application-status": "cancelled",
                                "application-cancellation_reason": "취소 사유",
                            }
                        )
                    ),
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "저장 실패")
                self.application.refresh_from_db()
                self.row.refresh_from_db()
                self.assertNotEqual(self.application.name, "실패 이름")
                self.assertEqual(self.row.state, "pending")
                self.assertEqual(self.application.history.count(), before)
                self.assertFalse(self.application.consultations.exists())

    def test_actions_and_consultation_permissions_cannot_be_forged(self):
        self.assertEqual(self.client.post(self.detail, {}).status_code, 400)
        for action in ("delete", "resend", "restore", "change_notification"):
            self.assertEqual(
                self.client.post(self.detail, {"action": action}).status_code, 400
            )
        self.client.force_login(self.changer)
        self.assertEqual(
            self.client.post(
                self.detail, self.payload(**self.consultation())
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete(self.detail).status_code, 405)
        self.assertTrue(
            EducationApplication.objects.filter(pk=self.application.pk).exists()
        )

    def test_database_failure_rolls_back_and_does_not_expose_error_or_payload(self):
        with patch(
            "education.models.ConsultationRecord.save",
            side_effect=DatabaseError("private DB detail"),
        ):
            response = self.client.post(
                self.detail,
                self.payload(
                    **self.consultation(
                        **{
                            "application-name": "저장실패 개인정보",
                            "application-status": "completed",
                        }
                    )
                ),
            )
        self.assertContains(
            response, "저장 결과를 확인하지 못했습니다", status_code=500
        )
        self.assertNotContains(response, "private DB detail", status_code=500)
        self.assertNotContains(response, "저장실패 개인정보", status_code=500)
        self.application.refresh_from_db()
        self.row.refresh_from_db()
        self.assertEqual(self.application.status, "received")
        self.assertEqual(self.row.state, "pending")
        self.assertFalse(self.application.consultations.exists())

    def test_email_status_modes_permissions_read_only_and_page_scripts(self):
        for state, label in (
            ("simulated", "모의 완료"),
            ("accepted", "SES 접수"),
            ("failed", "실패"),
            ("unknown", "결과 확인 필요"),
            ("suppressed", "발송 중단"),
        ):
            self.row.state = state
            self.row.save()
            response = self.client.get(self.email)
            self.assertContains(response, label)
            self.assertNotContains(response, "<html")
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.row.refresh_from_db()
            self.assertEqual(self.row.state, state)
        self.assertContains(
            self.client.get(self.detail), "backoffice-detail.js", count=1
        )
        self.assertNotContains(self.client.get(self.listing), "backoffice-detail.js")
        self.assertEqual(self.client.post(self.email).status_code, 405)
        self.client.logout()
        response = self.client.get(self.email)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Location", response.headers)
        self.assertNotContains(
            self.client.get(reverse("backoffice:login")), "backoffice-detail.js"
        )

    def test_post_auth_and_csrf_failures_never_echo_private_input(self):
        self.client.logout()
        response = self.client.post(
            self.detail, self.payload(**{"application-name": "秘密入力"})
        )
        self.assertContains(response, "저장하지 못했습니다", status_code=403)
        self.assertNotContains(response, "秘密入力", status_code=403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.editor)
        for url in (
            self.detail,
            reverse("backoffice:logout"),
            reverse("backoffice:login"),
        ):
            response = strict.post(url, {"application-name": "秘密入力"})
            self.assertEqual(response.status_code, 403)
            self.assertNotContains(response, "秘密入力", status_code=403)
        self.assertEqual(
            strict.post(reverse("education:application-api"), {}).status_code, 403
        )
        self.assertEqual(strict.post(reverse("admin:login"), {}).status_code, 403)
        self.application.refresh_from_db()
        self.assertNotEqual(self.application.name, "秘密入力")
