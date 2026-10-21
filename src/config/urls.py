"""공개 교육 페이지와 관리자 화면을 연결하고 개발 환경에서 미디어를 제공한다."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("education.urls")),
]

if settings.DEBUG and settings.SETTINGS_MODULE == "config.settings.dev":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
