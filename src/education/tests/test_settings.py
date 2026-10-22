import importlib
import importlib.util
import os
import runpy
import sys
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class SettingsTests(SimpleTestCase):
    """실행 환경과 분리해 환경 변수로 결정되는 설정 계약을 검증한다."""

    def setUp(self):
        # 실제 .env가 필수값 누락을 가리거나 테스트에 비밀값을 주입하지 않게 격리한다.
        root = Path(self.enterContext(TemporaryDirectory()))
        self.env_file = root / ".env"
        self.settings_dir = root / "src" / "config" / "settings"
        copytree(
            Path(__file__).resolve().parents[2] / "config" / "settings",
            self.settings_dir,
            ignore=lambda directory, names: ["__pycache__"],
        )
        self.environment = {
            "DJANGO_SECRET_KEY": "test-only-key",
            "POSTGRES_DB": "test_database",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test-only-password",
        }

    def _load_settings(self, mode="dev"):
        """격리된 .env와 환경 변수로 복사한 dev 또는 prod 설정 패키지를 로딩한다.

        이미 초기화된 Django settings나 모듈 캐시를 재사용하지 않아,
        환경 변수의 누락과 변경이 설정 로딩에 미치는 영향을 검증한다.

        Args:
            mode: 로딩할 dev 또는 prod 설정 모듈 이름.

        Returns:
            선택한 설정 모듈의 대문자 이름과 값만 담은 사전.

        Raises:
            ImproperlyConfigured: 필수 환경 변수가 없거나 비어 있거나,
                운영 설정의 DEBUG·host·CloudFront 도메인 계약을 위반한 경우.
        """
        package = "isolated_settings"
        spec = importlib.util.spec_from_file_location(
            package, self.settings_dir / "__init__.py"
        )
        with patch.dict(os.environ, self.environment, clear=True):
            sys.modules[package] = importlib.util.module_from_spec(spec)
            try:
                module = importlib.import_module(f"{package}.{mode}")
                return {
                    key: value for key, value in vars(module).items() if key.isupper()
                }
            finally:
                for name in list(sys.modules):
                    if name == package or name.startswith(f"{package}."):
                        del sys.modules[name]

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

    def _production_environment(self):
        self.environment.update(
            DJANGO_ALLOWED_HOSTS="education.example.com",
            AWS_STORAGE_BUCKET_NAME="example-education",
            AWS_S3_REGION_NAME="ap-northeast-2",
            AWS_S3_CUSTOM_DOMAIN="cdn.example.com",
            AWS_SES_REGION_NAME="ap-northeast-2",
            DEFAULT_FROM_EMAIL="no-reply@example.com",
            SES_MAX_SEND_RATE="2",
        )

    def test_dev_uses_local_media(self):
        from django.core.files.base import ContentFile
        from django.core.files.storage import FileSystemStorage

        configured = self._load_settings()
        storage = FileSystemStorage(
            location=configured["MEDIA_ROOT"], base_url=configured["MEDIA_URL"]
        )
        name = storage.save("education/example.txt", ContentFile(b"example"))
        self.assertEqual(storage.open(name).read(), b"example")
        self.assertEqual(storage.url(name), "/media/education/example.txt")

    def test_collectstatic_collects_project_and_admin_assets(self):
        """dev·prod 모두 원본과 분리한 로컬 경로에 프로젝트·admin 자산을 수집한다."""
        self._production_environment()
        for mode in ("dev", "prod"):
            with self.subTest(mode=mode):
                configured = self._load_settings(mode)
                destination = configured["STATIC_ROOT"]
                self.assertEqual(destination, self.env_file.parent / "staticfiles")
                self.assertNotIn(destination, configured["STATICFILES_DIRS"])
                self.assertNotEqual(destination, configured.get("MEDIA_ROOT"))
                with override_settings(
                    STATIC_ROOT=destination, STORAGES=configured["STORAGES"]
                ):
                    call_command("collectstatic", interactive=False, verbosity=0)
                for name in (
                    "css/site.css",
                    "js/application.js",
                    "js/backoffice-detail.js",
                ):
                    source = Path(__file__).resolve().parents[2] / "static" / name
                    self.assertEqual(
                        (destination / name).read_bytes(), source.read_bytes()
                    )
                self.assertTrue((destination / "admin/css/base.css").is_file())

    def test_background_and_email_environment_boundaries(self):
        configured = self._load_settings()
        self.assertEqual(configured["Q_CLUSTER"]["orm"], "default")
        self.assertEqual(configured["Q_CLUSTER"]["workers"], 2)
        self.assertNotIn("ALT_CLUSTERS", configured["Q_CLUSTER"])
        self.assertEqual(configured["NOTIFICATION_MODE"], "simulated")
        self.assertEqual(
            configured["MAILERS"]["default"]["BACKEND"],
            "django.core.mail.backends.locmem.EmailBackend",
        )
        self._production_environment()
        configured = self._load_settings("prod")
        self.assertEqual(configured["NOTIFICATION_MODE"], "ses")
        self.assertEqual(
            configured["MAILERS"]["default"]["BACKEND"], "django_ses.SESBackend"
        )
        self.assertEqual(configured["AWS_SES_CONFIG"].retries["total_max_attempts"], 1)
        self.assertIsNone(configured["AWS_SES_AUTO_THROTTLE"])
        self.assertNotIn("AWS_SES_CONFIGURATION_SET", configured)

    def test_prod_requires_email_settings_and_valid_rate(self):
        self._production_environment()
        for name in ("AWS_SES_REGION_NAME", "DEFAULT_FROM_EMAIL", "SES_MAX_SEND_RATE"):
            original = self.environment.pop(name)
            with self.assertRaisesMessage(ImproperlyConfigured, name):
                self._load_settings("prod")
            self.environment[name] = original
        for value in ("0", "-1", "nan", "inf", "invalid"):
            self.environment["SES_MAX_SEND_RATE"] = value
            with self.assertRaisesMessage(ImproperlyConfigured, "SES_MAX_SEND_RATE"):
                self._load_settings("prod")

    def test_prod_generates_cloudfront_url_without_aws_calls(self):
        from storages.backends.s3 import S3Storage

        self._production_environment()
        configured = self._load_settings("prod")
        self.assertIs(configured["DEBUG"], False)
        options = configured["STORAGES"]["default"]["OPTIONS"]
        with patch("boto3.Session", side_effect=AssertionError("AWS 호출 금지")):
            self.assertEqual(
                S3Storage(**options).url("education/example.jpg"),
                "https://cdn.example.com/media/education/example.jpg",
            )

    def test_prod_rejects_missing_settings_and_debug(self):
        self._production_environment()
        for name in (
            "DJANGO_ALLOWED_HOSTS",
            "AWS_STORAGE_BUCKET_NAME",
            "AWS_S3_REGION_NAME",
            "AWS_S3_CUSTOM_DOMAIN",
        ):
            with self.subTest(name=name):
                original = self.environment.pop(name)
                with self.assertRaisesMessage(ImproperlyConfigured, name):
                    self._load_settings("prod")
                self.environment[name] = original
        self.environment["DJANGO_DEBUG"] = "true"
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_DEBUG"):
            self._load_settings("prod")

    def test_prod_rejects_domain_with_scheme_path_or_query(self):
        self._production_environment()
        for value in (
            "https://cdn.example.com",
            "cdn.example.com/",
            "cdn.example.com?a=b",
            "cdn..example.com",
        ):
            with self.subTest(value=value):
                self.environment["AWS_S3_CUSTOM_DOMAIN"] = value
                with self.assertRaisesMessage(
                    ImproperlyConfigured, "AWS_S3_CUSTOM_DOMAIN"
                ):
                    self._load_settings("prod")

    def test_entrypoints_preserve_explicit_settings_and_default_to_dev(self):
        root = Path(__file__).resolve().parents[2]
        for selected in (None, "config.settings.prod"):
            for path, target in (
                (
                    root / "manage.py",
                    "django.core.management.execute_from_command_line",
                ),
                (root / "config/asgi.py", "django.core.asgi.get_asgi_application"),
                (root / "config/wsgi.py", "django.core.wsgi.get_wsgi_application"),
            ):
                with self.subTest(selected=selected, path=path.name):
                    environment = (
                        {} if selected is None else {"DJANGO_SETTINGS_MODULE": selected}
                    )
                    with patch.dict(os.environ, environment, clear=True), patch(target):
                        runpy.run_path(str(path), run_name="__main__")
                        self.assertEqual(
                            os.environ["DJANGO_SETTINGS_MODULE"],
                            selected or "config.settings.dev",
                        )

    def test_settings_flag_selects_prod(self):
        import subprocess

        self._production_environment()
        environment = os.environ.copy()
        environment.update(self.environment, DJANGO_DEBUG="false")
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "manage.py"),
                "shell",
                "--settings=config.settings.prod",
                "-c",
                "from django.conf import settings; assert settings.SETTINGS_MODULE == 'config.settings.prod'",
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, "명시적 prod settings 선택 실패")

    def test_dev_does_not_import_aws_backend(self):
        import subprocess

        # 앞선 테스트의 AWS import 이력이 판정을 오염시키지 않도록 새 프로세스를 쓴다.
        code = (
            "import os, sys; import django; "
            "os.environ['DJANGO_SETTINGS_MODULE']='config.settings.dev'; django.setup(); "
            "assert 'storages.backends.s3' not in sys.modules; "
            "assert 'boto3' not in sys.modules"
        )
        environment = os.environ.copy()
        environment.update(self.environment)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, "dev에서 AWS 모듈이 로딩됨")

    def test_media_route_is_dev_debug_only(self):
        from django.test import override_settings
        from django.urls import Resolver404, clear_url_caches, resolve

        import config.urls

        try:
            for mode, debug in (("dev", True), ("dev", False), ("prod", False)):
                with override_settings(
                    DEBUG=debug,
                    SETTINGS_MODULE=f"config.settings.{mode}",
                    MEDIA_URL="/media/",
                    MEDIA_ROOT="unused",
                ):
                    urls = importlib.reload(config.urls)
                    clear_url_caches()
                    if mode == "dev" and debug:
                        self.assertEqual(
                            resolve("/media/image.jpg", urls).url_name, None
                        )
                    else:
                        with self.assertRaises(Resolver404):
                            resolve("/media/image.jpg", urls)
        finally:
            # 변경한 URL 모듈과 resolver 캐시가 다른 테스트에 남지 않게 복원한다.
            importlib.reload(config.urls)
            clear_url_caches()
