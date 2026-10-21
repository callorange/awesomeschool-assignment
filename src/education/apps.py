from django.apps import AppConfig


class EducationConfig(AppConfig):
    name = "education"

    def ready(self):
        """교육 삭제·이미지 교체의 commit 후 파일 정리 signal을 등록한다."""
        from . import signals  # noqa: F401
