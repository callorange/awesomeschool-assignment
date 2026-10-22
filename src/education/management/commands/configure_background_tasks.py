"""동일 이름의 안내 검사 스케줄을 중복 없이 준비한다."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django_q.models import Schedule


class Command(BaseCommand):
    help = "5분 간격 안내 검사 스케줄을 준비합니다. 외부 발송은 실행하지 않습니다."

    @transaction.atomic
    def handle(self, *args, **options):
        """전용 이름의 스케줄만 갱신·중복 정리하고 기존 다음 실행 시각은 유지한다."""
        rows = Schedule.objects.select_for_update().filter(
            name="education-notifications"
        )
        schedule = rows.order_by("pk").first()
        if schedule is None:
            schedule = Schedule(name="education-notifications")
        schedule.func = "education.tasks.enqueue_consultation_reminder_emails"
        schedule.schedule_type = Schedule.MINUTES
        schedule.minutes, schedule.repeats, schedule.cluster = 5, -1, "default"
        schedule.save()
        rows.exclude(pk=schedule.pk).delete()
        self.stdout.write("안내 검사 스케줄 준비 완료 (5분 간격)")
