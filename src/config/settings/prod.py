"""명시적인 운영 설정으로 S3 미디어와 SES 이메일 backend를 선택한다."""

import math

from botocore.config import Config
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_domain_name, validate_email

from . import base
from .base import *  # noqa: F403

if base.DEBUG:
    raise ImproperlyConfigured("운영에서는 DJANGO_DEBUG를 활성화할 수 없습니다.")
DEBUG = False
if not base.ALLOWED_HOSTS or "*" in base.ALLOWED_HOSTS:
    raise ImproperlyConfigured("운영 DJANGO_ALLOWED_HOSTS를 명시해야 합니다.")

_bucket = base._required_env("AWS_STORAGE_BUCKET_NAME")
_region = base._required_env("AWS_S3_REGION_NAME")
_domain = base._required_env("AWS_S3_CUSTOM_DOMAIN")
try:
    validate_domain_name(_domain)
except ValidationError:
    raise ImproperlyConfigured(
        "AWS_S3_CUSTOM_DOMAIN은 경로 없는 유효한 host여야 합니다."
    ) from None

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": _bucket,
            "region_name": _region,
            "custom_domain": _domain,
            "location": "media",
            "url_protocol": "https:",
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": False,
            "cloudfront_signer": None,
            "client_config": Config(
                connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1}
            ),
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

AWS_SES_REGION_NAME = base._required_env("AWS_SES_REGION_NAME")
DEFAULT_FROM_EMAIL = base._required_env("DEFAULT_FROM_EMAIL")
try:
    validate_email(DEFAULT_FROM_EMAIL)
except ValidationError:
    raise ImproperlyConfigured(
        "DEFAULT_FROM_EMAIL은 유효한 이메일이어야 합니다."
    ) from None
try:
    SES_MAX_SEND_RATE = float(base._required_env("SES_MAX_SEND_RATE"))
except ValueError:
    raise ImproperlyConfigured("SES_MAX_SEND_RATE는 양수여야 합니다.") from None
if not math.isfinite(SES_MAX_SEND_RATE) or SES_MAX_SEND_RATE <= 0:
    raise ImproperlyConfigured("SES_MAX_SEND_RATE는 유한한 양수여야 합니다.")
MAILERS = {"default": {"BACKEND": "django_ses.SESBackend"}}
NOTIFICATION_MODE = "ses"
USE_SES_V2 = True
AWS_SES_AUTO_THROTTLE = None
# worker 공통 DB 예산과 오류 분류가 전송 횟수를 제어하도록 SDK의 내부 재시도를 막는다.
AWS_SES_CONFIG = Config(
    connect_timeout=5, read_timeout=15, retries={"total_max_attempts": 1}
)
