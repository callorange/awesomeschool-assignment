"""
Project-level URL routing for the initial Django setup.

Only Django's built-in admin URLs are registered here. Education pages and
application APIs will be connected in subsequent feature changes.
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
