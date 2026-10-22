"""빈 개발 DB의 단일 초기 migration과 프리셋·스케줄 준비를 검증한다."""

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django_q.models import Schedule

from education.models import (
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
)


class EducationMigrationTests(TransactionTestCase):
    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_empty_database_initial_migration_seed_and_schedule(self):
        media = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(override_settings(MEDIA_ROOT=media))
        executor = MigrationExecutor(connection)
        self.assertEqual(
            {
                name
                for app, name in executor.loader.disk_migrations
                if app == "education"
            },
            {"0001_initial"},
        )
        self.addCleanup(self.restore_schema)
        executor.migrate([("education", None)])
        self.assertNotIn(
            Education._meta.db_table, connection.introspection.table_names()
        )
        self.restore_schema()
        for model in (
            Education,
            EducationApplication,
            EducationApplicationReminderEmail,
        ):
            self.assertIn(model._meta.db_table, connection.introspection.table_names())
            self.assertFalse(model.objects.exists())
        for _ in range(2):
            call_command("seed_educations", stdout=StringIO())
            call_command("configure_background_tasks", stdout=StringIO())
        self.assertEqual(Education.objects.count(), 3)
        identifiers = list(Education.objects.values_list("media_id", flat=True))
        self.assertEqual(len(set(identifiers)), 3)
        self.assertTrue(all(identifier.version == 7 for identifier in identifiers))
        for education in Education.objects.all():
            self.assertTrue((media / education.image.name).is_file())
        schedule = Schedule.objects.get(name="education-notifications")
        self.assertEqual(
            schedule.func, "education.tasks.enqueue_consultation_reminder_emails"
        )
        self.assertEqual(
            (schedule.minutes, schedule.repeats, schedule.cluster), (5, -1, "default")
        )
