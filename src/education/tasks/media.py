"""미참조 교육 이미지 정리 task의 저장소 호출과 오류 처리를 담당한다."""

from django.core.files.storage import storages

from ..models import Education
from .exceptions import SafeTaskError


def delete_unreferenced_education_image(name, storage_alias="default", using="default"):
    """현재 DB 참조를 재확인한 뒤 지정된 Storage의 미참조 파일만 삭제한다.

    Args:
        name: Storage 기준 상대 파일 키. 큐에는 파일 객체 대신 이 키를 저장한다.
        storage_alias: storages에서 선택할 저장소 alias.
        using: 교육 참조를 조회할 DB alias.

    Returns:
        참조가 있거나 키가 비어 있으면 "preserved", 삭제 요청 완료 시 "deleted".
        이미 없는 파일의 성공 처리는 각 Storage.delete 계약을 따른다.

    Raises:
        SafeTaskError: 저장소 삭제 실패. Q2 제한 재시도를 위해 예외를 전달하되
            원문 대신 파일 키와 예외 종류만 남긴다.
    """
    if not name or Education.objects.using(using).filter(image=name).exists():
        return "preserved"
    try:
        storages[storage_alias].delete(name)
    except Exception as error:
        raise SafeTaskError(f"media:{name}:{type(error).__name__}") from None
    return "deleted"
