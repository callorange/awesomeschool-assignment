"""신규 교육 이미지의 경로를 구성한다.

historical migration에서 upload_to 함수를 참조하므로 import 경로를 유지한다.
"""

from pathlib import PurePosixPath
from uuid import UUID, uuid4


def education_image_path(media_id, filename):
    """교육별 이미지의 후보 키를 만들며 저장소에는 접근하지 않는다.

    Args:
        media_id: 교육 생성 시 부여한 고정 UUID 또는 UUID 문자열.
        filename: 호출자가 생성한 디렉터리 없는 파일명.

    Returns:
        education/<UUID의 32자 hex>/images/ 아래의 저장소 상대 키.

    Raises:
        ValueError: media_id가 유효한 UUID 문자열이 아닌 경우.
    """
    identifier = media_id if isinstance(media_id, UUID) else UUID(media_id)
    return f"education/{identifier.hex}/images/{filename}"


def education_image_upload_to(instance, filename):
    """FileField 저장 시 원본 basename을 UUID로 바꾼 후보 키를 반환한다.

    instance의 media_id는 생성 시 정해지므로 DB 저장과 PK 발급이 필요하지 않다.
    확장자는 소문자로 유지하지만 파일 변환이나 형식 검증은 하지 않는다.
    최종 키는 충돌 처리 후 Storage가 반환하는 이름을 사용해야 한다.

    Args:
        instance: 이미지를 연결할 Education 인스턴스.
        filename: FileField가 전달한 원본 파일명.

    Returns:
        교육별 경로와 UUID 파일명으로 구성한 저장소 상대 키.

    Raises:
        ValueError: instance.media_id가 유효한 UUID 문자열이 아닌 경우.
    """
    extension = PurePosixPath(filename).suffix.lower()
    return education_image_path(instance.media_id, f"{uuid4().hex}{extension}")
