"""교육 삭제·이미지 교체가 commit된 뒤 미참조 파일만 정리한다."""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Education

logger = logging.getLogger(__name__)


def _queue_image_cleanup(name, storage, using):
    """지정한 DB의 commit 이후 미참조 파일 정리를 예약한다.

    활성 transaction이 없으면 즉시 실행하며 rollback되면 실행하지 않는다.
    빈 키는 무시하고 실행 시 참조를 다시 확인해 공유·재연결된 파일을 보존한다.
    조회나 삭제 실패는 로그만 남기며 이미 commit된 DB 변경은 되돌리지 않는다.

    Args:
        name: 삭제 후보인 이전 파일의 저장소 상대 키.
        storage: 해당 파일이 속한 Storage 객체.
        using: 참조 조회와 on_commit 등록에 사용할 DB alias.
    """
    if not name:
        return

    def cleanup():
        """commit 시점의 참조를 확인해 미참조 파일만 삭제하고 실패를 기록한다."""
        try:
            if not Education.objects.using(using).filter(image=name).exists():
                storage.delete(name)
        except Exception as error:
            # 저장소 예외 본문에는 접속 정보가 포함될 수 있어 종류만 기록한다.
            logger.error(
                "교육 이미지 정리 실패: key=%s, error=%s", name, type(error).__name__
            )

    transaction.on_commit(cleanup, using=using, robust=True)


@receiver(post_delete, sender=Education)
def cleanup_deleted_education_image(sender, instance, using, **kwargs):
    """단일·일괄 삭제된 교육의 이미지 정리를 DB commit 이후로 예약한다."""
    _queue_image_cleanup(instance.image.name, instance.image.storage, using)


@receiver(pre_save, sender=Education)
def remember_previous_image(sender, instance, using, raw, update_fields, **kwargs):
    """교체 전 이미지 키를 같은 DB에서 읽어 post_save에 전달한다.

    instance._previous_image_name은 저장 시도마다 초기화한다. fixture의 raw
    저장·PK 없는 생성·image를 제외한 update_fields 저장은 교체를 검사하지 않는다.
    파일 저장과 실제 반환 키 결정은 이후 FileField 처리에 맡긴다.
    """
    instance._previous_image_name = None
    if (
        raw
        or instance.pk is None
        or (update_fields is not None and "image" not in update_fields)
    ):
        return
    instance._previous_image_name = (
        sender.objects.using(using)
        .filter(pk=instance.pk)
        .values_list("image", flat=True)
        .first()
    )


@receiver(post_save, sender=Education)
def cleanup_replaced_education_image(sender, instance, using, raw, **kwargs):
    """저장된 실제 키가 바뀌면 이전 파일만 commit 이후 정리하도록 예약한다.

    새 파일이나 동일 키는 정리하지 않으며 raw fixture 저장은 건너뛴다.
    이전 키는 pre_save에서 수집하므로 이를 우회하는 bulk 수정은 처리하지 않는다.
    """
    if raw:
        return
    previous = getattr(instance, "_previous_image_name", None)
    if previous and previous != instance.image.name:
        _queue_image_cleanup(previous, instance.image.storage, using)
