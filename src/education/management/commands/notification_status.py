"""개인정보 없이 메일 처리 현황과 결과 확인이 필요한 시도를 조회한다."""

from django.core.management.base import BaseCommand
from django.db.models import Count

from education.models import ApplicationNotification


class Command(BaseCommand):
    help = "메일 상태별 건수와 확인 필요 시도를 조회합니다. 상태 변경·재발송은 하지 않습니다."

    def handle(self, *args, **options):
        """상태별 건수와 확인 대상의 ID·오류 코드만 출력하며 DB 상태는 변경하지 않는다."""
        for row in (
            ApplicationNotification.objects.values("state")
            .annotate(total=Count("pk"))
            .order_by("state")
        ):
            self.stdout.write(f"{row['state']}: {row['total']}")
        rows = ApplicationNotification.objects.filter(
            state__in=["unknown", "sending", "failed"]
        ).order_by("pk")
        for row in rows.iterator():
            self.stdout.write(
                f"notification={row.pk} attempt={row.attempt_id} state={row.state} code={row.error_code}"
            )
