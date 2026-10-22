"""교육 변경과 동일 transaction에 미참조 이미지 정리 후보를 영속 등록한다."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django_q.tasks import async_task

from .models import Education


@receiver(pre_delete, sender=Education)
def preserve_application_education_history(sender, instance, using, **kwargs):
    """Collector의 SET_NULL이 signal을 우회하기 전에 신청 연결 해제를 기록한다."""
    for application in instance.applications.using(using).all():
        application.education = None
        application._history_user = None
        application._change_reason = "원본 교육 삭제로 연결 해제"
        application.save(using=using, update_fields=["education"])


def _queue_image_cleanup(name, using):
    """같은 DB의 ORM broker에 키를 기록하고 등록 실패는 교육 변경도 rollback한다."""
    if not name:
        return
    if settings.Q_CLUSTER["orm"] != using:
        raise ImproperlyConfigured("이미지 변경 DB와 Q2 ORM broker DB가 같아야 합니다.")
    async_task(
        "education.tasks.delete_unreferenced_education_image",
        name,
        "default",
        using,
        ack_failure=False,
    )


@receiver(post_delete, sender=Education)
def cleanup_deleted_education_image(sender, instance, using, **kwargs):
    """Django 삭제 transaction 안에 파일 키를 등록한다. 실행 시 참조를 다시 검사한다."""
    _queue_image_cleanup(instance.image.name, using)


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
    """저장된 실제 키가 바뀌면 Education.save transaction 안에 이전 키를 등록한다.

    새 파일이나 동일 키는 정리하지 않으며 raw fixture 저장은 건너뛴다.
    이전 키는 pre_save에서 수집하므로 이를 우회하는 bulk 수정은 처리하지 않는다.
    """
    if raw:
        return
    previous = getattr(instance, "_previous_image_name", None)
    if previous and previous != instance.image.name:
        _queue_image_cleanup(previous, using)
