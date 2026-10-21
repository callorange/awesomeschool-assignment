from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe

from .models import Education


@require_safe
def landing(request):
    """로그인 없이 표시 순서에 따른 교육 목록과 빈 목록 안내를 제공한다."""
    return render(
        request, "education/landing.html", {"educations": Education.objects.all()}
    )


@require_safe
def detail(request, slug):
    """교육 상세를 공개하고 등록되지 않은 slug는 HTTP 404로 응답한다."""
    education = get_object_or_404(Education, slug=slug)
    return render(request, "education/detail.html", {"education": education})
