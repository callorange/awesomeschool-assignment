"""기본 admin과 분리된 담당자용 업무 URL이다."""

from django.urls import path

from . import backoffice

app_name = "backoffice"
urlpatterns = [
    path("", backoffice.index, name="index"),
    path("login/", backoffice.Login.as_view(), name="login"),
    path("logout/", backoffice.Logout.as_view(), name="logout"),
    path("applications/", backoffice.application_list, name="application-list"),
    path(
        "applications/<int:pk>/",
        backoffice.application_detail,
        name="application-detail",
    ),
    path(
        "applications/<int:pk>/email-status/",
        backoffice.email_status,
        name="email-status",
    ),
]
