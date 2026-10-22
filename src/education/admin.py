"""신청·상담은 보존하고 내부 안내 기록은 조회만 가능한 기본 admin이다."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from .forms.application import EducationApplicationForm
from .forms.consultation import ConsultationForm, NewConsultationFormSet
from .forms.education import EducationForm
from .models import (
    ConsultationRecord,
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
    MailAttempt,
    MailSendBudget,
)
from .services.applications import EDITABLE_FIELDS, save_application


class NoDeleteAdmin(admin.ModelAdmin):
    actions = None

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(NoDeleteAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Education)
class EducationAdmin(NoDeleteAdmin):
    form = EducationForm
    list_display = ("title", "slug", "operation_type", "is_accepting_inquiries")
    search_fields = ("title", "slug")
    list_filter = ("operation_type", "is_accepting_inquiries")
    readonly_fields = ("media_id",)


class FollowUpFilter(admin.SimpleListFilter):
    """오늘 예정과 기한 경과는 겹칠 수 있으며 일정 미정은 별도로 조회한다."""

    title = "재연락 대상"
    parameter_name = "follow_up"

    def lookups(self, request, model_admin):
        return (
            ("today", "오늘 예정"),
            ("overdue", "기한 경과"),
            ("undated", "일정 미정"),
        )

    def queryset(self, request, queryset):
        if self.value() not in ("today", "overdue", "undated"):
            return queryset
        queryset = queryset.filter(status=EducationApplication.Status.FOLLOW_UP)
        if self.value() == "today":
            return queryset.filter(next_contact_at__date=timezone.localdate())
        if self.value() == "overdue":
            return queryset.filter(next_contact_at__lt=timezone.now())
        return queryset.filter(next_contact_at__isnull=True)


class ConsultationHistoryInline(admin.TabularInline):
    model = ConsultationRecord
    fields = (
        "created_at",
        "author",
        "result",
        "content",
        "next_contact_at",
        "corrects",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(
            "education.view_educationapplication"
        ) and super().has_view_permission(request, obj)


class NewConsultationInline(admin.StackedInline):
    """기존 기록 조회 영역과 분리해 새 상담 한 건만 추가한다."""

    model = ConsultationRecord
    formset = NewConsultationFormSet
    fields = ("result", "content", "corrects")
    extra = 1
    max_num = 1
    can_delete = False
    verbose_name_plural = "새 상담 기록 추가"

    def get_queryset(self, request):
        return super().get_queryset(request).none()

    def has_view_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm(
            "education.view_educationapplication"
        ) and super().has_add_permission(request, obj)


@admin.register(EducationApplication)
class EducationApplicationAdmin(SimpleHistoryAdmin, NoDeleteAdmin):
    form = EducationApplicationForm
    list_display = (
        "education_title",
        "name",
        "email",
        "contact_date",
        "status",
        "next_contact_at",
        "created_at",
    )
    search_fields = ("name", "email")
    list_filter = ("education_title", "status", "contact_date", FollowUpFilter)
    ordering = ("-created_at", "-pk")
    readonly_fields = (
        "education",
        "education_slug",
        "education_title",
        "request_id",
        "submission_snapshot",
        "created_at",
    )
    inlines = (ConsultationHistoryInline, NewConsultationInline)
    history_list_display = ("status", "next_contact_at")

    def has_add_permission(self, request):
        return False

    def get_inlines(self, request, obj):
        inlines = list(super().get_inlines(request, obj))
        if request.user.has_perm("education.view_educationapplicationreminderemail"):
            inlines.append(ReminderEmailInline)
        return inlines

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """폼을 읽기 전 처리권을 잠가 검증과 저장 사이 발송 경합도 방지한다."""
        if request.method == "POST" and object_id:
            if not self.has_change_permission(request):
                raise PermissionDenied
            with transaction.atomic():
                EducationApplicationReminderEmail.objects.select_for_update().filter(
                    application_id=object_id
                ).first()
                EducationApplication.objects.select_for_update().filter(
                    pk=object_id
                ).first()
                return super().changeform_view(
                    request, object_id, form_url, extra_context
                )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """서비스가 저장한 값을 admin 인스턴스에도 반영해 inline과 상태를 맞춘다."""
        saved = save_application(
            obj.pk,
            {
                field: form.cleaned_data[field]
                for field in EDITABLE_FIELDS
                if field in form.cleaned_data
            },
            request.user,
        )
        for field in EDITABLE_FIELDS:
            setattr(obj, field, getattr(saved, field))

    def save_formset(self, request, form, formset, change):
        """작성자와 변경 후 연락 예정은 요청의 transaction 안에서 서버 값으로 기록한다."""
        for record in formset.save(commit=False):
            record.author = request.user
            record.next_contact_at = form.instance.next_contact_at
            record.save()
        formset.save_m2m()

    def history_form_view(self, request, object_id, version_id, extra_context=None):
        """패키지의 복원 버튼 숨김은 POST를 막지 않으므로 서버에서도 거부한다."""
        if request.method not in ("GET", "HEAD"):
            raise PermissionDenied
        return super().history_form_view(request, object_id, version_id, extra_context)

    def has_view_history_or_change_history_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_change_history_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if (
            request.resolver_match.url_name
            == "education_educationapplication_simple_history"
        ):
            return tuple(field.name for field in self.model._meta.fields)
        return super().get_readonly_fields(request, obj)


@admin.register(ConsultationRecord)
class ConsultationAdmin(ReadOnlyAdmin):
    form = ConsultationForm
    list_display = ("application", "created_at", "author", "result", "next_contact_at")
    list_select_related = ("application", "author")
    list_filter = ("result", "created_at")
    search_fields = ("application__name", "application__email")

    def has_module_permission(self, request):
        return request.user.has_perm(
            "education.view_educationapplication"
        ) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(
            "education.view_educationapplication"
        ) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return request.user.has_perm(
            "education.view_educationapplication"
        ) and request.user.has_perm("education.add_consultationrecord")

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) if obj else ()

    def get_fields(self, request, obj=None):
        return (
            super().get_fields(request, obj)
            if obj
            else ("application", "result", "content", "corrects")
        )

    def save_model(self, request, obj, form, change):
        """부모 신청을 잠가 관리 일정 변경과 일관된 시점의 상담 snapshot을 기록한다."""
        application = EducationApplication.objects.select_for_update().get(
            pk=obj.application_id
        )
        obj.author = request.user
        obj.next_contact_at = application.next_contact_at
        obj.save()


class ReminderEmailInline(admin.StackedInline):
    model = EducationApplicationReminderEmail
    extra = 0
    can_delete = False
    fields = (
        "state",
        "due_at",
        "mode",
        "attempt_count",
        "sent_at",
        "simulated_at",
        "error_code",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EducationApplicationReminderEmail)
class ReminderEmailAdmin(ReadOnlyAdmin):
    list_display = ("application_id", "state", "due_at", "mode", "attempt_count")
    list_filter = ("state", "mode")


@admin.register(MailAttempt)
class MailAttemptAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "notification_id",
        "state",
        "started_at",
        "finished_at",
        "error_code",
    )
    list_filter = ("state",)


@admin.register(MailSendBudget)
class MailSendBudgetAdmin(ReadOnlyAdmin):
    list_display = ("id", "next_allowed_at")
