"""고정 교육 프리셋을 선택한 저장소에 넣고 기존 교육과 이미지는 보존한다."""

import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.media import education_image_path
from education.models import Education

PRESET_PATH = settings.BASE_DIR.parent / "presets/education/education_presets.json"


def _load_presets():
    """DB나 저장소에 쓰지 않고 전체 프리셋과 이미지 원본을 검증한다.

    프리셋 images 폴더의 PNG만 허용하며 고정 UUIDv7과 내용 해시로 키를 만든다.
    UUID는 프리셋에 기록해 실패 후 재실행에서도 같은 파일을 재사용한다.
    수집 기록은 프리셋에만 남기고 slug·UUID 중복도 거부한다.

    Returns:
        모델 필드 값 사전과 이미지 bytes를 짝지은 목록. image 값은 원본 경로가 아닌
        저장소 상대 이름이며 수집 기록은 모델 필드 사전에 포함하지 않는다.

    Raises:
        OSError: 프리셋 또는 이미지 파일을 읽을 수 없는 경우.
        ValueError: JSON·이미지 형식·목록·교시 순서나 slug 중복이 잘못된 경우.
        TypeError: 레코드나 필드 구조가 올바르지 않은 경우.
        KeyError: 필수 키가 없는 경우.
        ValidationError: 모델 필드의 값이 유효하지 않은 경우.
    """
    records = json.loads(PRESET_PATH.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("교육 프리셋 목록이 필요합니다.")
    prepared = []
    slugs = set()
    media_ids = set()
    for record in records:
        fields = dict(record)
        for key in ("source_url", "source_image_url", "collected_on", "editorial_note"):
            fields.pop(key, None)
        media_id = Education._meta.get_field("media_id").to_python(fields["media_id"])
        if media_id is None or media_id.version != 7 or media_id in media_ids:
            raise ValueError("프리셋마다 고유한 UUIDv7 media_id가 필요합니다.")
        media_ids.add(media_id)
        fields["media_id"] = media_id
        image_path = (PRESET_PATH.parent / fields.pop("image")).resolve()
        if not image_path.is_relative_to((PRESET_PATH.parent / "images").resolve()):
            raise ValueError("이미지는 프리셋 images 안에 있어야 합니다.")
        content = image_path.read_bytes()
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG 이미지 원본이 필요합니다.")
        digest = hashlib.sha256(content).hexdigest()
        fields["image"] = education_image_path(media_id, f"{digest}.png")
        education = Education(**fields)
        # 기존 교육은 재실행에서 보존하므로 DB slug 중복 검사는 생성 단계에 맡긴다.
        education.full_clean(validate_unique=False)
        if education.slug in slugs:
            raise ValueError("중복 교육 slug입니다.")
        slugs.add(education.slug)
        prepared.append((fields, content))
    return prepared


class Command(BaseCommand):
    help = "교육 3개와 이미지를 초기화합니다. 기존 교육·이미지는 변경하지 않습니다."

    def handle(self, *args, **options):
        """없는 교육만 생성하고 선택된 기본 Storage에 필요한 이미지를 저장한다.

        입력 전체를 먼저 검증하며 기존 교육과 연결 이미지는 변경하지 않는다.
        같은 이름의 이미지는 실패 후 재실행에서도 재사용하고, 새로 저장할 때는
        Storage가 실제로 반환한 이름을 DB에 기록한다. 생성·건너뜀 건수를 출력한다.

        Raises:
            CommandError: 입력 검증 또는 초기화 실패. 쓰기 중 오류는 DB 변경을
                롤백하지만 이미 저장한 파일은 남을 수 있어 자동 삭제하지 않는다.
        """
        try:
            prepared = _load_presets()
        except (OSError, ValueError, TypeError, KeyError, ValidationError) as error:
            raise CommandError(f"교육 프리셋 검증 실패: {error}") from error

        created_count = 0
        saved_names = []
        try:
            with transaction.atomic():
                for fields, content in prepared:
                    slug = fields["slug"]
                    education, created = Education.objects.get_or_create(
                        slug=slug, defaults=fields
                    )
                    if not created:
                        continue
                    name = fields["image"]
                    if not default_storage.exists(name):
                        name = default_storage.save(name, ContentFile(content))
                        saved_names.append(name)
                    if education.image.name != name:
                        education.image = name
                        education.save(update_fields=["image"])
                    created_count += 1
        except Exception as error:
            # Storage 쓰기는 DB transaction에 포함되지 않아 자동 삭제하지 않는다.
            if saved_names:
                self.stderr.write(
                    f"저장소에 파일 {len(saved_names)}개가 남을 수 있습니다. "
                    "기존 파일은 삭제하지 않았으며 재실행 시 재사용합니다."
                )
            raise CommandError(
                f"교육 초기화 실패 ({type(error).__name__}). DB 변경을 롤백했습니다."
            ) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"생성 {created_count}개, 건너뜀 {len(prepared) - created_count}개"
            )
        )
