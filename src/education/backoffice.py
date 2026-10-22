"""담당자용 신청 관리와 권한을 공유하는 이메일 상태 부분 조회를 제공한다."""

from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView, redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.csrf import csrf_failure as default_csrf_failure
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .forms.backoffice import BackofficeApplicationForm, BackofficeConsultationForm
from .models import EducationApplication, EducationApplicationReminderEmail
from .services.applications import EDITABLE_FIELDS, save_application


class Login(LoginView):
    """기존 활성 staff 계정으로 로그인하고 admin과 동일한 세션을 사용한다."""

    template_name = "backoffice/login.html"
    authentication_form = AdminAuthenticationForm
    next_page = reverse_lazy("backoffice:application-list")


class Logout(LogoutView):
    next_page = reverse_lazy("backoffice:login")


@never_cache
def csrf_failure(request, reason=""):
    """백오피스 CSRF 실패는 입력 복구 없이 안내하고 다른 경로는 기본 처리한다.

    settings의 CSRF_FAILURE_VIEW 진입점이다. reason과 제출 개인정보를 업무
    오류 화면에 전달하지 않아 인증 실패가 원문 입력의 재출력으로 이어지지 않는다.
    """
    if request.path.startswith(reverse("backoffice:index")):
        return render(request, "backoffice/save_denied.html", status=403)
    return default_csrf_failure(request, reason=reason)


def _access(request, *, partial=False):
    """활성 staff와 신청 조회 권한을 확인하고 요청 종류별 인증 실패를 반환한다.

    부분 조회는 로그인 HTML을 이메일 영역에 삽입하지 않도록 미인증 401을
    반환한다. 일반 POST의 미인증은 저장 없는 403이며 GET만 로그인으로 이동한다.
    신청 변경·상담·메일 조회 권한은 각 작업에서 별도로 검사해야 한다.

    Returns:
        접근 가능하면 None, 미인증이면 요청 종류에 맞는 오류 또는 redirect 응답.

    Raises:
        PermissionDenied: 로그인했지만 활성 staff·신청 조회 조건을 충족하지 않는 경우.
    """
    if not request.user.is_authenticated:
        if partial:
            return HttpResponse(status=401)
        if request.method == "POST":
            return render(request, "backoffice/save_denied.html", status=403)
        return redirect_to_login(request.get_full_path(), reverse("backoffice:login"))
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("education.view_educationapplication")
    ):
        raise PermissionDenied
    return None


@never_cache
@require_GET
def index(request):
    denied = _access(request)
    return denied or redirect("backoffice:application-list")


def _filter_applications(request, rows):
    """GET 조건을 적용한 queryset을 반환하며 평가·정렬·페이지 분할은 하지 않는다.

    교육은 원본 연결이 아닌 신청 당시 교육명으로 필터링한다. 재연락의 오늘·기한
    경과는 한국 시각 기준으로 겹칠 수 있고 일정 미정은 별도 조건이다. 알 수 없는
    재연락 필터값은 무시하되 교육·상태의 미일치 값은 빈 결과가 된다.
    """
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(email__icontains=query))
    for field in ("education_title", "status"):
        if value := request.GET.get(field):
            rows = rows.filter(**{field: value})
    follow_up = request.GET.get("follow_up")
    if follow_up in ("today", "overdue", "undated"):
        rows = rows.filter(status=EducationApplication.Status.FOLLOW_UP)
        if follow_up == "today":
            rows = rows.filter(next_contact_at__date=timezone.localdate())
        elif follow_up == "overdue":
            rows = rows.filter(next_contact_at__lt=timezone.now())
        else:
            rows = rows.filter(next_contact_at__isnull=True)
    return rows


@never_cache
@require_GET
def application_list(request):
    """권한 있는 담당자에게 검색 조건을 보존하는 최신순 20건 목록을 제공한다.

    교육 선택지도 신청 snapshot에서 구성해 원본 교육 삭제 후에도 검색 가능하게
    한다. 잘못되거나 범위를 벗어난 페이지 번호는 Paginator.get_page로 정리한다.
    """
    denied = _access(request)
    if denied:
        return denied
    rows = _filter_applications(request, EducationApplication.objects.all())
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "backoffice/application_list.html",
        {
            "page_obj": Paginator(rows.order_by("-created_at", "-pk"), 20).get_page(
                request.GET.get("page")
            ),
            "query_string": params.urlencode(),
            "education_titles": EducationApplication.objects.order_by("education_title")
            .values_list("education_title", flat=True)
            .distinct(),
            "statuses": EducationApplication.Status.choices,
        },
    )


def _forms(request, application, *, bound=False):
    """권한과 저장 의도에 따라 신청·상담 폼을 만들고 오류 재표시 입력을 유지한다.

    bound=True이면 신청 폼은 POST를 사용하고 상담은 명시적으로 추가를 요청한
    경우에만 bind한다. 미선택 상담까지 template 렌더링 중 검증되는 것을 막는다.
    폼을 숨기는 것은 작업 인가를 대신하지 않으며 _operation에서 다시 확인한다.

    Returns:
        신청 폼과 상담 폼의 tuple. 각 쓰기 권한이 없으면 해당 위치는 None이다.
    """
    data = request.POST if bound else None
    consultation_data = (
        data
        if bound
        and (
            request.POST.get("action") == "add_consultation"
            or request.POST.get("include_consultation") == "on"
        )
        else None
    )
    application_form = (
        BackofficeApplicationForm(data, instance=application, prefix="application")
        if request.user.has_perm("education.change_educationapplication")
        else None
    )
    consultation_form = (
        BackofficeConsultationForm(
            consultation_data,
            application=application,
            can_view=request.user.has_perm("education.view_consultationrecord"),
            prefix="consultation",
        )
        if request.user.has_perm("education.add_consultationrecord")
        else None
    )
    return application_form, consultation_form


def _operation(request):
    """직접 POST에도 저장 의도와 필요한 모델 권한을 적용한다.

    부모 신청 조회 권한은 _access를 통과한 상태여야 한다. 상담 전용 추가는
    신청 변경 권한을 요구하지 않지만 통합 저장에 상담을 포함하면 두 권한이 필요하다.

    Returns:
        작업명과 상담 포함 여부의 tuple. 누락·알 수 없는 작업은 None이며 호출자가
        400으로 처리한다.

    Raises:
        PermissionDenied: 선택한 작업에 필요한 신청 변경·상담 추가 권한이 없는 경우.
    """
    action = request.POST.get("action")
    if action not in ("save_application", "add_consultation"):
        return None
    include = (
        action == "add_consultation" or request.POST.get("include_consultation") == "on"
    )
    if action == "save_application" and not request.user.has_perm(
        "education.change_educationapplication"
    ):
        raise PermissionDenied
    if include and not request.user.has_perm("education.add_consultationrecord"):
        raise PermissionDenied
    return action, include


def _save(request, pk, action, include):
    """폼 검증 전 잠근 최신 신청·안내와 선택 상담을 한 transaction에 저장한다.

    worker와 같은 안내→신청 잠금 순서를 폼 검증 전부터 유지한다. 통합 저장은
    기존 서비스로 신청·이력·안내를 조정한 뒤 변경 후 일정으로 상담을 기록한다.
    상담 전용 추가는 신청을 검증·변경하지 않고 잠근 현재 일정을 기록한다.
    저장 중 예외는 transaction 밖으로 전달되어 부분 저장을 rollback한다.

    Args:
        request: _access와 _operation의 권한 검사를 마친 POST 요청.
        pk: 안내가 연결된 기존 신청의 PK.
        action: 검증된 save_application 또는 add_consultation 작업명.
        include: 상담 추가를 명시적으로 요청했는지 여부.

    Returns:
        저장 성공은 None, 폼 유효성 실패는 입력·오류를 보존한 신청/상담 폼 tuple.

    Raises:
        Http404: 잠글 신청 또는 연결 안내가 없는 경우.
        ValidationError: 저장 서비스·모델의 최종 검증 실패. 호출자가 폼에 표시한다.
        DatabaseError: DB 저장·commit 실패. 호출자가 안전한 오류 화면을 제공한다.
    """
    with transaction.atomic():
        get_object_or_404(
            EducationApplicationReminderEmail.objects.select_for_update(),
            application_id=pk,
        )
        application = get_object_or_404(
            EducationApplication.objects.select_for_update(), pk=pk
        )
        application_form, consultation_form = _forms(request, application, bound=True)
        valid_application = action != "save_application" or application_form.is_valid()
        valid_consultation = not include or consultation_form.is_valid()
        if not (valid_application and valid_consultation):
            return application_form, consultation_form
        if action == "save_application":
            application = save_application(
                pk,
                {
                    field: application_form.cleaned_data[field]
                    for field in EDITABLE_FIELDS
                },
                request.user,
            )
        if include:
            record = consultation_form.save(commit=False)
            record.author = request.user
            record.next_contact_at = application.next_contact_at
            record.save()
    return None


@never_cache
@require_http_methods(["GET", "POST"])
def application_detail(request, pk):
    """신청 상세를 조회하거나 권한별 신청·상담 작업을 원자적으로 저장한다.

    상담·메일은 별도 조회 권한이 있는 경우에만 template context에 포함한다.
    폼/최종 검증 오류는 입력을 유지하고 DB 오류는 원문·POST를 출력하지 않는
    500 안내로 처리한다. 성공 후 GET redirect는 새로고침 재제출을 막지만 모든
    POST 재전송에 대한 중복 방지를 보장하지는 않는다.
    """
    denied = _access(request)
    if denied:
        return denied
    application = get_object_or_404(EducationApplication, pk=pk)
    forms = _forms(request, application)
    if request.method == "POST":
        operation = _operation(request)
        if operation is None:
            return HttpResponse(status=400)
        try:
            forms = _save(request, pk, *operation)
        except ValidationError as exc:
            forms = _forms(request, application, bound=True)
            target = forms[0] if operation[0] == "save_application" else forms[1]
            target.is_valid()
            target.add_error(None, " ".join(exc.messages))
        except DatabaseError:
            return render(request, "backoffice/save_failed.html", status=500)
        if forms is None:
            messages.success(request, "저장했습니다.")
            return redirect("backoffice:application-detail", pk=pk)
    context = {
        "application": application,
        "application_form": forms[0],
        "consultation_form": forms[1],
        "include_consultation": request.POST.get("include_consultation") == "on",
    }
    if request.user.has_perm("education.view_consultationrecord"):
        context["consultations"] = application.consultations.select_related(
            "author", "corrects"
        )
    if request.user.has_perm("education.view_educationapplicationreminderemail"):
        context["notification"] = application.notification
    return render(request, "backoffice/application_detail.html", context)


@never_cache
@require_GET
def email_status(request, pk):
    """신청·메일 조회 권한으로 보호한 이메일 상태 HTML 조각만 반환한다.

    상세 최초 표시와 같은 template를 사용하며 DB 조회 외 발송·저장 동작은 없다.
    미인증 401·인가 실패 403은 로그인 HTML로 redirect하지 않고 클라이언트가
    기존 표시와 편집 입력을 유지한 채 안내하도록 한다.
    """
    denied = _access(request, partial=True)
    if denied:
        return denied
    if not request.user.has_perm("education.view_educationapplicationreminderemail"):
        raise PermissionDenied
    application = get_object_or_404(EducationApplication, pk=pk)
    return render(
        request,
        "backoffice/email_status.html",
        {"notification": application.notification},
    )
