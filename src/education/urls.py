from django.urls import path

from . import views

app_name = "education"
urlpatterns = [
    path("", views.landing, name="landing"),
    path("educations/<slug:slug>/", views.detail, name="detail"),
]
