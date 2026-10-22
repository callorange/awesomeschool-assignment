from django.urls import path

from . import api, views

app_name = "education"
urlpatterns = [
    path("educations/<slug:slug>/apply/", views.application, name="application"),
    path(
        "api/educations/<slug:slug>/",
        api.EducationDetailAPI.as_view(),
        name="education-api",
    ),
    path(
        "api/applications/",
        api.EducationApplicationCreateAPI.as_view(),
        name="application-api",
    ),
    path("", views.landing, name="landing"),
    path("educations/<slug:slug>/", views.detail, name="detail"),
]
