"""고정 교육 프리셋을 선택한 저장소에 넣고 기존 교육과 이미지는 보존한다."""

import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Education

PRESET_PATH = settings.BASE_DIR.parent / "presets/education/education_presets.json"


def _validate_curriculum(curriculum):
    """시수별 교시가 누락 없이 순서대로 제공되는지 검사한다.

    각 과정의 periods는 중복 없는 양의 정수여야 하며 lessons의 길이와 같아야 한다.
    교시는 1부터 시작하는 연속된 period와 비어 있지 않은 주제·활동·설명을 가진다.

    Raises:
        ValueError: 목록·시수·교시 순서 또는 문자열 내용이 올바르지 않은 경우.
        KeyError: 과정이나 교시의 필수 키가 없는 경우.
        TypeError: 과정이나 교시가 키로 접근할 수 있는 구조가 아닌 경우.
    """
    if not isinstance(curriculum, list) or not curriculum:
        raise ValueError("커리큘럼 목록이 필요합니다.")
    periods = set()
    for course in curriculum:
        length = course["periods"]
        lessons = course["lessons"]
        if type(length) is not int or length < 1 or length in periods:
            raise ValueError("시수 구성이 올바르지 않습니다.")
        periods.add(length)
        if not isinstance(lessons, list) or len(lessons) != length:
            raise ValueError("시수와 교시 수가 다릅니다.")
        for number, lesson in enumerate(lessons, 1):
            if type(lesson["period"]) is not int or lesson["period"] != number:
                raise ValueError("교시 순서가 올바르지 않습니다.")
            _validate_texts(
                [lesson[key] for key in ("topic", "activity", "description")]
            )


def _validate_texts(values):
    """빈 목록·공백 문자열·문자열 이외의 항목은 ValueError로 거부한다."""
    if not isinstance(values, list) or not values:
        raise ValueError("비어 있지 않은 문자열 목록이 필요합니다.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("비어 있지 않은 문자열이 필요합니다.")


def _load_presets():
    """DB나 저장소에 쓰지 않고 전체 프리셋과 이미지 원본을 검증한다.

    프리셋 images 폴더의 PNG만 허용하며 slug와 내용 해시로 저장소 상대 이름을 만든다.
    날짜는 모델 검증을 통해 정규화하고 프리셋 안의 slug 중복도 거부한다.

    Returns:
        모델 필드 값 사전과 이미지 bytes를 짝지은 목록. image 값은 원본 경로가 아닌
        저장소 상대 이름이며 collected_on은 검증된 날짜다.

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
    for record in records:
        fields = dict(record)
        image_path = (PRESET_PATH.parent / fields.pop("image")).resolve()
        if not image_path.is_relative_to((PRESET_PATH.parent / "images").resolve()):
            raise ValueError("이미지는 프리셋 images 안에 있어야 합니다.")
        content = image_path.read_bytes()
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG 이미지 원본이 필요합니다.")
        digest = hashlib.sha256(content).hexdigest()
        fields["image"] = f"education/presets/{fields['slug']}-{digest}.png"
        education = Education(**fields)
        # 기존 교육은 재실행에서 보존하므로 DB slug 중복 검사는 생성 단계에 맡긴다.
        education.full_clean(validate_unique=False)
        _validate_texts(education.goals)
        _validate_texts(education.audiences)
        _validate_curriculum(education.curriculum)
        if education.slug in slugs:
            raise ValueError("중복 교육 slug입니다.")
        slugs.add(education.slug)
        fields["collected_on"] = education.collected_on
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
