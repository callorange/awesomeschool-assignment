"""명시적인 운영 설정으로 S3에 저장하고 CloudFront로 미디어를 제공한다."""

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_domain_name

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
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
