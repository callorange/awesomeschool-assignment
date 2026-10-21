"""로컬 파일시스템 미디어와 기존 개발 환경 변수 계약을 사용한다."""

from . import base
from .base import *  # noqa: F403

MEDIA_ROOT = base.BASE_DIR.parent / "media"
MEDIA_URL = "/media/"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
