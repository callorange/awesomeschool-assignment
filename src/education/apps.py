from django.apps import AppConfig


class EducationConfig(AppConfig):
    name = "education"

    def ready(self):
        """교육 변경 transaction의 파일 정리 큐 등록 signal을 연결한다."""
        from . import signals  # noqa: F401
