import os
import runpy
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class SettingsTests(SimpleTestCase):
    """실행 환경과 분리해 환경 변수로 결정되는 설정 계약을 검증한다."""

    def setUp(self):
        # 실제 .env가 필수값 누락을 가리거나 테스트에 비밀값을 주입하지 않게 격리한다.
        root = Path(self.enterContext(TemporaryDirectory()))
        self.env_file = root / ".env"
        self.settings_file = root / "src" / "config" / "settings.py"
        self.settings_file.parent.mkdir(parents=True)
        copyfile(
            Path(__file__).resolve().parents[2] / "config" / "settings.py",
            self.settings_file,
        )
        self.environment = {
            "DJANGO_SECRET_KEY": "test-only-key",
            "POSTGRES_DB": "test_database",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test-only-password",
        }

    def _load_settings(self):
        """격리된 .env와 환경 변수로 실제 설정 파일의 복사본을 새로 실행한다.

        이미 초기화된 Django settings나 모듈 캐시를 재사용하지 않아,
        환경 변수의 누락과 변경이 설정 로딩에 미치는 영향을 검증한다.

        Returns:
            설정 파일 실행으로 생성된 이름과 값의 매핑.

        Raises:
            ImproperlyConfigured: 필수 환경 변수가 없거나 비어 있는 경우.
        """
        with patch.dict(os.environ, self.environment, clear=True):
            return runpy.run_path(str(self.settings_file))

    def test_env_file_is_loaded_from_repository_root(self):
        """현재 작업 디렉터리 대신 설정 파일 위치로 .env를 찾는지 검증한다."""
        self.env_file.write_text(
            "\n".join(f"{name}={value}" for name, value in self.environment.items())
            + "\nDJANGO_DEBUG=true\nDJANGO_ALLOWED_HOSTS=localhost,127.0.0.1\n",
            encoding="utf-8",
        )
        self.environment.clear()
        configured = self._load_settings()
        self.assertEqual(configured["SECRET_KEY"], "test-only-key")
        self.assertEqual(configured["DATABASES"]["default"]["NAME"], "test_database")
        self.assertIs(configured["DEBUG"], True)
        self.assertEqual(configured["ALLOWED_HOSTS"], ["localhost", "127.0.0.1"])

    def test_process_environment_overrides_env_file(self):
        self.env_file.write_text(
            "POSTGRES_DB=file_database\nDJANGO_DEBUG=true\n", encoding="utf-8"
        )
        self.environment["DJANGO_DEBUG"] = "false"
        configured = self._load_settings()
        self.assertEqual(configured["DATABASES"]["default"]["NAME"], "test_database")
        self.assertIs(configured["DEBUG"], False)

    def test_empty_process_value_is_not_replaced_by_env_file(self):
        """빈 필수 환경 변수를 .env 값으로 대체해 설정 오류를 숨기지 않는다."""
        self.env_file.write_text("POSTGRES_PASSWORD=file-password\n", encoding="utf-8")
        self.environment["POSTGRES_PASSWORD"] = ""
        with self.assertRaisesMessage(ImproperlyConfigured, "POSTGRES_PASSWORD"):
            self._load_settings()

    def test_debug_defaults_to_false(self):
        self.assertIs(self._load_settings()["DEBUG"], False)

    def test_debug_parses_true_and_false(self):
        for value, expected in [
            ("true", True),
            ("false", False),
            (" TRUE ", True),
            ("1", True),
            ("0", False),
        ]:
            with self.subTest(value=value):
                self.environment["DJANGO_DEBUG"] = value
                self.assertIs(self._load_settings()["DEBUG"], expected)

    def test_allowed_hosts_are_trimmed_and_empty_entries_ignored(self):
        self.environment["DJANGO_ALLOWED_HOSTS"] = " localhost, 127.0.0.1, ,"
        self.assertEqual(
            self._load_settings()["ALLOWED_HOSTS"], ["localhost", "127.0.0.1"]
        )

    def test_required_environment_fails_without_disclosing_values(self):
        """필수값의 누락·빈 값을 거부하고 오류에 설정값이 노출되지 않음을 검증한다."""
        # 각 사례에서 키를 제거·복원하므로 순회할 키 목록을 고정한다.
        for name in tuple(self.environment):
            for missing_value in [None, ""]:
                with self.subTest(name=name, missing_value=missing_value):
                    original = self.environment.pop(name)
                    if missing_value is not None:
                        self.environment[name] = missing_value
                    try:
                        with self.assertRaises(ImproperlyConfigured) as error:
                            self._load_settings()
                        self.assertIn(name, str(error.exception))
                        for value in self.environment.values():
                            if value:
                                self.assertNotIn(value, str(error.exception))
                    finally:
                        self.environment[name] = original

    def test_database_and_localization_settings(self):
        """DB 접속 없이 PostgreSQL 기본 연결 설정과 지역화 정책을 확인한다."""
        configured = self._load_settings()
        self.assertEqual(
            configured["DATABASES"]["default"]["ENGINE"],
            "django.db.backends.postgresql",
        )
        self.assertEqual(configured["DATABASES"]["default"]["HOST"], "127.0.0.1")
        self.assertEqual(configured["LANGUAGE_CODE"], "ko-kr")
        self.assertEqual(configured["TIME_ZONE"], "Asia/Seoul")
        self.assertIs(configured["USE_TZ"], True)
