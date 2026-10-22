"""교육과 선택한 개발 신청 샘플을 준비하고 기존 데이터·이미지를 보존한다."""

import hashlib
import json
from collections import Counter
from datetime import datetime, time

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from education.media import education_image_path
from education.models import (
    ConsultationRecord,
    Education,
    EducationApplication,
    EducationApplicationReminderEmail,
    MailAttempt,
)

PRESET_PATH = settings.BASE_DIR.parent / "presets/education/education_presets.json"
APPLICATION_PRESET_PATH = PRESET_PATH.with_name("application_presets.json")


def _sample_staff(options):
    """샘플 옵션의 개발 모의 환경과 명시적으로 지정한 기존 담당자를 확인한다.

    USERNAME_FIELD로 조회만 하며 계정·권한·비밀번호를 생성하거나 변경하지 않는다.
    개발 설정으로 연결한 DB 자체가 개발용인지 판별하는 기능은 제공하지 않는다.

    Returns:
        신청 옵션이 없으면 None, 있으면 상담 작성자로 연결할 기존 활성 staff.

    Raises:
        CommandError: 옵션 조합·설정 모듈·메일 모드/backend 또는 담당자가 부적합한 경우.
    """
    if not options["with_applications"]:
        if options["staff_user"]:
            raise CommandError("--staff-user는 --with-applications와 함께 지정하세요.")
        return None
    if (
        settings.SETTINGS_MODULE != "config.settings.dev"
        or settings.NOTIFICATION_MODE != "simulated"
        or settings.MAILERS["default"]["BACKEND"]
        != "django.core.mail.backends.locmem.EmailBackend"
    ):
        raise CommandError(
            "신청 샘플은 dev 설정·simulated·locmem 환경에서만 허용합니다."
        )
    user_model = get_user_model()
    user = user_model.objects.filter(
        **{user_model.USERNAME_FIELD: options["staff_user"]},
        is_active=True,
        is_staff=True,
    ).first()
    if user is None:
        raise CommandError("--staff-user에 기존 활성 staff 사용자명을 지정하세요.")
    return user


def _prepare_consultations(records, application, author, now):
    """상담 상대 시각·원기록 참조를 쓰기 전에 검증하고 미저장 모델을 반환한다.

    Args:
        records: 작성 순서의 상담 정의. hours_after_application은 접수 후 시간이며
            정정의 corrects는 같은 목록에서 앞선 원기록의 0부터 시작하는 인덱스다.
        application: 접수 시각과 현재 재연락 일정이 계산된 샘플 신청.
        author: 호출자가 확인한 기존 활성 staff. 모든 새 상담에 연결한다.
        now: 신청과 같은 기준으로 확보한 한국 시각의 aware datetime.

    Returns:
        (미저장 상담, 정정 대상 인덱스 또는 None) 목록. 신청·정정 FK 연결과 최종
        모델 검증은 실제 저장 시 수행하며 현재 신청 일정을 당시 일정으로 사용한다.

    Raises:
        ValidationError: 상담 필드가 모델 검증에 실패한 경우.
        ValueError: 내용·작성 시각·재연락 일정 또는 정정 대상의 관계가 잘못된 경우.
    """
    prepared = []
    for record in records:
        fields = dict(record)
        corrects = fields.pop("corrects", None)
        created_at = application.created_at + relativedelta(
            hours=fields.pop("hours_after_application")
        )
        consultation = ConsultationRecord(
            **fields,
            author=author,
            created_at=created_at,
            next_contact_at=application.next_contact_at,
        )
        consultation.clean_fields(exclude=["application", "corrects"])
        if not consultation.content.strip() or not (
            application.created_at <= created_at <= now
        ):
            raise ValueError("상담 내용 또는 시각이 잘못되었습니다.")
        if prepared and created_at < prepared[-1][0].created_at:
            raise ValueError("상담은 작성 시각 순서로 정의해야 합니다.")
        if consultation.next_contact_at and created_at > consultation.next_contact_at:
            raise ValueError("재연락 합의 상담은 예정 시각 이전이어야 합니다.")
        is_correction = consultation.result == ConsultationRecord.Result.CORRECTION
        if is_correction != (corrects is not None) or (
            corrects is not None and not 0 <= corrects < len(prepared)
        ):
            raise ValueError("정정 대상은 같은 신청의 앞선 상담이어야 합니다.")
        prepared.append((consultation, corrects))
    return prepared


def _prepare_notification(state, application, now, retry_minutes):
    """발송·큐 등록 없이 화면 확인용 안내와 시도를 미저장 상태로 구성한다.

    모두 simulated 모드이며 accepted·SES 접수 증거는 만들지 않는다. queued는
    표시용 시각만 갖고 실제 Q2 작업은 없으므로 worker의 만료 복구 대상이 된다.

    Args:
        state: 구성할 모의 안내 상태. 완료·취소 신청에는 대기 상태를 허용하지 않는다.
        application: 연락 가능 날짜와 접수 시각이 계산된 샘플 신청.
        now: 신청과 같은 기준으로 확보한 한국 시각의 aware datetime.
        retry_minutes: 현재부터 재시도 허용 시각까지의 분 단위 offset. retry_wait에만
            사용하며 합성 시도 종료 후 5분보다 이르게 허용하지 않는다.

    Returns:
        (미저장 안내, 미저장 시도 또는 None). pending·queued·suppressed는 시도가 없고
        나머지는 연결 전의 현재 시도 한 건과 일치하는 attempt_id·횟수를 가진다.

    Raises:
        ValueError: 상태 조합이 잘못됐거나 처리 사례의 대상 시각이 아직 오지 않은 경우.
    """
    State = EducationApplicationReminderEmail.State
    if state not in State.values or state == State.ACCEPTED:
        raise ValueError("샘플 이메일 상태가 잘못되었습니다.")
    if application.status in EducationApplication.TERMINAL_STATUSES and state in (
        State.PENDING,
        State.QUEUED,
        State.SENDING,
        State.RETRY_WAIT,
    ):
        raise ValueError("종료된 신청에 대기 중인 안내를 구성할 수 없습니다.")
    morning = datetime.combine(application.contact_date, time(9), tzinfo=now.tzinfo)
    row = EducationApplicationReminderEmail(
        mode="simulated", state=state, due_at=max(morning, application.created_at)
    )
    if state in (State.PENDING, State.SUPPRESSED):
        return row, None
    if row.due_at > now:
        raise ValueError("처리된 안내의 대상 시각은 현재 이후일 수 없습니다.")
    # 새벽 실행에도 대상·시작·종료 순서를 지키도록 유효 구간 안에 시각을 배분한다.
    started = row.due_at + (now - row.due_at) / 2
    if state == State.QUEUED:
        row.queued_at = started
        return row, None
    finished = started + (now - started) / 2
    code = (
        f"preset_simulated_{state}"
        if state in (State.RETRY_WAIT, State.FAILED, State.UNKNOWN)
        else ""
    )
    attempt = MailAttempt(
        state=state,
        started_at=started,
        finished_at=None if state == State.SENDING else finished,
        error_code=code,
    )
    row.attempt_count, row.attempt_id, row.started_at = 1, attempt.pk, started
    row.error_code = code
    if state == State.SIMULATED:
        row.simulated_at = finished
    elif state == State.RETRY_WAIT:
        row.next_retry_at = max(
            finished + relativedelta(minutes=5),
            now + relativedelta(minutes=retry_minutes),
        )
    return row, attempt


def _load_applications(educations, author, now):
    """고정 신청 입력 전체를 검증하고 신규 저장용 모델과 종속 기록을 준비한다.

    날짜는 이번 실행 기준으로 계산하지만 기존 request_id의 현재 값과는 비교하지
    않는다. 공개 접수·업무 변경 서비스의 오늘 이후 제한을 바꾸지 않고 과거 샘플을
    구성하되 접수 이후 관계는 검증한다. DB·Storage 쓰기는 수행하지 않는다.

    Args:
        educations: 교육 slug를 기존 또는 미저장 Education에 연결한 매핑.
            신청 당시 교육명은 이 교육의 현재 title을 사용한다.
        author: 새 상담에 연결할 기존 활성 staff.
        now: 이번 실행에서 한 번 확보한 한국 시각의 aware datetime.

    Returns:
        (미저장 신청, 상담/정정 인덱스 목록, 미저장 안내, 미저장 시도 또는 None)의
        목록. 교육 연결과 최초 제출 snapshot·history 생성은 저장 단계에 맡긴다.

    Raises:
        OSError: 신청 프리셋 파일을 읽을 수 없는 경우.
        KeyError: 필수 키 또는 연결할 교육 slug가 없는 경우.
        TypeError: 프리셋 구조·모델 인자·상대 날짜 값의 타입이 잘못된 경우.
        ValidationError: 신청·상담 필드가 모델 검증에 실패한 경우.
        ValueError: JSON·식별자·배분·가상 이메일 또는 날짜·상담·메일 관계가 잘못된 경우.
    """
    records = json.loads(APPLICATION_PRESET_PATH.read_text(encoding="utf-8"))
    prepared = []
    for record in records:
        fields = dict(record)
        consultations = fields.pop("consultations")
        state = fields.pop("email_state")
        retry_minutes = fields.pop("retry_minutes_from_now", -5)
        created_at = now - relativedelta(days=fields.pop("created_days_ago"), hours=2)
        contact_date = max(
            created_at.date(),
            now.date() + relativedelta(days=fields.pop("contact_days_from_today")),
        )
        next_days = fields.pop("next_contact_days_from_today")
        next_contact = (
            None
            if next_days is None
            else now
            + relativedelta(days=next_days, hour=14, minute=0, second=0, microsecond=0)
        )
        application = EducationApplication(
            **fields,
            education_title=educations[fields["education_slug"]].title,
            created_at=created_at,
            contact_date=contact_date,
            next_contact_at=next_contact,
        )
        application.full_clean(
            exclude=["education", "submission_snapshot"], validate_unique=False
        )
        if created_at > now or (next_contact and next_contact < created_at):
            raise ValueError("신청과 재연락 시각의 선후 관계가 잘못되었습니다.")
        if (application.status != "follow_up" and next_contact) or (
            application.status == "cancelled"
            and not application.cancellation_reason.strip()
        ):
            raise ValueError("신청 상태에 맞는 일정과 취소 사유가 필요합니다.")
        if not application.email.endswith("@example.com"):
            raise ValueError("샘플 이메일은 example.com이어야 합니다.")
        row, attempt = _prepare_notification(state, application, now, retry_minutes)
        prepared.append(
            (
                application,
                _prepare_consultations(consultations, application, author, now),
                row,
                attempt,
            )
        )
    applications = [item[0] for item in prepared]
    if (
        len(applications) != 32
        or len({item.request_id for item in applications}) != 32
        or Counter(item.education_slug for item in applications)
        != {"prompt-hero": 11, "emotion-hero": 11, "relationship-hero": 10}
        or Counter(item.status for item in applications)
        != {
            "received": 8,
            "consulting": 6,
            "follow_up": 10,
            "completed": 4,
            "cancelled": 4,
        }
    ):
        raise ValueError("신청 샘플의 식별자 또는 교육·상태 배분이 잘못되었습니다.")
    return prepared


def _save_applications(prepared, educations):
    """고정 식별자가 있으면 신청 단위로 보존하고 새 신청의 종속 기록만 저장한다.

    호출자는 교육 저장을 포함한 outer transaction.atomic 안에서 실행해야 한다.
    내부 atomic은 동시 request_id 충돌을 처리하는 savepoint이며 실행 전체의
    rollback 경계를 대신하지 않는다. 기존 신청은 불변 최초 이메일·교육 slug만
    대조하고 현재값·날짜·종속 기록은 수정하거나 누락분을 복구하지 않는다.

    Args:
        prepared: _load_applications가 반환한 미저장 모델과 상담 참조 목록.
        educations: 교육 slug를 실제 저장된 Education에 연결한 매핑.

    Returns:
        종속 기록까지 새로 저장한 신청 수. 기존 식별자의 건너뜀은 제외한다.

    Raises:
        ValueError: 기존 식별자의 불변 최초 입력이 샘플과 충돌하는 경우.
        ValidationError: 안내·시도·상담의 최종 모델 검증에 실패한 경우.
        IntegrityError: 같은 request_id의 동시 생성으로 설명할 수 없는 무결성 오류.
            다른 DB 저장 오류도 호출자에게 전달해 전체 transaction을 rollback한다.
    """
    created_count = 0
    for application, consultations, row, attempt in prepared:
        existing = EducationApplication.objects.filter(
            request_id=application.request_id
        ).first()
        if existing:
            if any(
                existing.submission_snapshot[field] != getattr(application, field)
                for field in ("email", "education_slug")
            ):
                raise ValueError("샘플 식별자가 기존 신청의 최초 입력과 충돌합니다.")
            continue
        application.education = educations[application.education_slug]
        # 가상 초기 상태를 실제 담당자의 과거 변경 행위로 기록하지 않는다.
        application._history_user = None
        application._history_date = application.created_at
        application._change_reason = "개발 샘플 초기 상태 (실제 상담·발송 이력 아님)"
        try:
            with transaction.atomic():
                application.save(force_insert=True)
        except IntegrityError:
            # 생성 이력 속성을 유지하면서 동시 생성은 DB unique 제약으로 조정한다.
            existing = EducationApplication.objects.filter(
                request_id=application.request_id
            ).first()
            if existing is None:
                raise
            if any(
                existing.submission_snapshot[field] != getattr(application, field)
                for field in ("email", "education_slug")
            ):
                raise ValueError("샘플 식별자가 기존 신청의 최초 입력과 충돌합니다.")
            continue
        row.application = application
        row.full_clean()
        row.save()
        if attempt:
            attempt.notification = row
            attempt.full_clean()
            attempt.save()
        saved_consultations = []
        for consultation, corrects in consultations:
            consultation.application = application
            if corrects is not None:
                consultation.corrects = saved_consultations[corrects]
            consultation.save()
            saved_consultations.append(consultation)
        created_count += 1
    return created_count


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

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-applications",
            action="store_true",
            help="개발용 신청 샘플 32건도 준비합니다.",
        )
        parser.add_argument(
            "--staff-user", help="샘플 상담 작성자로 사용할 기존 활성 staff 사용자명"
        )

    def handle(self, *args, **options):
        """없는 교육과 선택한 신청 샘플을 함께 저장하고 기존 레코드는 건너뛴다.

        입력 전체를 먼저 검증하며 기존 교육과 연결 이미지는 변경하지 않는다.
        같은 이름의 이미지는 실패 후 재실행에서도 재사용하고, 새로 저장할 때는
        Storage가 실제로 반환한 이름을 DB에 기록한다. 생성·건너뜀 건수를 출력한다.
        신청 옵션은 지정한 기존 staff와 개발 모의 환경에서만 허용하며 상담·안내·
        시도·생성 이력을 함께 저장하고 발송이나 큐 등록은 수행하지 않는다.

        Raises:
            CommandError: 입력 검증 또는 초기화 실패. 쓰기 중 오류는 DB 변경을
                롤백하지만 이미 저장한 파일은 남을 수 있어 자동 삭제하지 않는다.
        """
        author = _sample_staff(options)
        applications = []
        now = timezone.localtime(timezone.now())
        try:
            prepared = _load_presets()
            if author:
                educations = {
                    fields["slug"]: Education.objects.filter(
                        slug=fields["slug"]
                    ).first()
                    or Education(**fields)
                    for fields, _ in prepared
                }
                applications = _load_applications(educations, author, now)
        except (OSError, ValueError, TypeError, KeyError, ValidationError) as error:
            raise CommandError(
                f"프리셋 검증 실패 ({type(error).__name__}). 입력을 확인하세요."
            ) from error

        created_count = 0
        application_count = 0
        saved_names = []
        educations = {}
        try:
            with transaction.atomic():
                for fields, content in prepared:
                    slug = fields["slug"]
                    education = Education.objects.filter(slug=slug).first()
                    if education:
                        educations[slug] = education
                        continue
                    name = fields["image"]
                    if not default_storage.exists(name):
                        name = default_storage.save(name, ContentFile(content))
                        saved_names.append(name)
                    # 반환 키를 최초 저장에 써 이미지 교체 정리 작업의 큐 등록을 피한다.
                    education, created = Education.objects.get_or_create(
                        slug=slug, defaults={**fields, "image": name}
                    )
                    educations[slug] = education
                    created_count += int(created)
                if author:
                    application_count = _save_applications(applications, educations)
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
        if author:
            self.stdout.write(
                self.style.SUCCESS(
                    f"신청 생성 {application_count}개, 건너뜀 {len(applications) - application_count}개. "
                    "화면 확인용 합성 상태이며 실제 상담·메일 발송 증거가 아닙니다."
                )
            )
