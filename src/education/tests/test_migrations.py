"""빈 개발 DB의 통합 migration과 프리셋 초기화를 실제 PostgreSQL에서 검증한다."""

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

from education.models import Education


class EducationMigrationTests(TransactionTestCase):
    """0001의 빈 테이블에 Django가 생성한 0002를 적용하는 계약을 검사한다.

    UUID 고유 필드와 수집 기록 제거를 포함하므로 기존 데이터 업그레이드가 아닌
    사용자가 승인한 개발 DB 초기화 흐름을 검증한다.
    """

    def test_empty_database_upgrade_and_seed(self):
        media = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=media))
        executor = MigrationExecutor(connection)
        self.addCleanup(self.restore_schema)
        executor.migrate([("education", "0001_initial")])
        self.assertFalse(
            executor.loader.project_state([("education", "0001_initial")])
            .apps.get_model("education", "Education")
            .objects.exists()
        )
        self.restore_schema()
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, Education._meta.db_table
                )
            }
        for name in (
            "source_url",
            "source_image_url",
            "collected_on",
            "editorial_note",
        ):
            self.assertNotIn(name, columns)
        call_command("seed_educations", stdout=StringIO())
        self.assertEqual(Education.objects.count(), 3)
        identifiers = list(Education.objects.values_list("media_id", flat=True))
        self.assertEqual(len(set(identifiers)), 3)
        self.assertTrue(all(identifier.version == 7 for identifier in identifiers))
        for education in Education.objects.all():
            self.assertTrue((media / education.image.name).is_file())

    def restore_schema(self):
        """실패한 경우에도 후속 테스트가 사용할 최신 schema로 복원한다."""
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
