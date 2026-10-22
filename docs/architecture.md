# 아키텍처와 기술 선택

교육 소개 → 신청 접수 → 신청 관리라는 하나의 흐름을 단일 Django 프로젝트에서 구현합니다. 교육 소개·상담 신청과 담당자용 백오피스는 Django Templates와 Tailwind CSS로 제공하고 기본 Django admin도 유지합니다. 실행 명령과 구현 상태는 [README](../README.md), 원래 요구사항은 [과제 문서](awesomeschool-assignment.md)를 기준으로 합니다.

## 프로젝트 구조

| 경로 | 책임 |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.python-version` | Python·의존성·개발 도구와 실행 환경 |
| `compose.yaml`, `.env.example` | 로컬 PostgreSQL과 환경 변수 계약 |
| `src/manage.py` | Django 관리 명령 진입점 |
| `src/config/` | 설정·URL·ASGI·WSGI 진입점 |
| `src/education/` | 교육·신청·안내 모델, 공개 API·화면, 백오피스, 메일·이미지 작업과 관리 명령 |
| `src/education/backoffice.py`, `src/education/backoffice_urls.py` | 담당자 로그인·신청 목록/상세·저장·이메일 상태 HTML 부분 조회 |
| `src/education/forms/` | 교육·신청·상담별 admin·백오피스 입력 폼과 교육 콘텐츠 위젯 |
| `src/education/services/applications.py` | 신청 변경 검증과 신청·이력·안내의 transaction 저장 |
| `src/education/tasks/` | 기존 Q2 함수 경로 공개·안내 등록/발송·메일 처리 단계·이미지 정리 |
| `src/education/migrations/0001_initial.py` | 전체 모델을 빈 DB에 생성하는 초기 migration |
| `src/templates/` | 공통 layout과 기능별 template를 담는 통합 폴더 |
| `src/static/` | 빌드 CSS·JS·source map·라이선스 고지 등 배포 정적 자산을 담는 통합 폴더 |
| `frontend/`, `package.json`, `package-lock.json` | CSS·JavaScript 소스, 통합 빌드 명령·의존성 설치 조합 |
| `presets/education/` | 초기화용 JSON 프리셋과 이미지 원본 |
| `src/education/tests/` | 설정·모델·프리셋·공개 화면·백오피스·admin·API·메일·이미지·qcluster 테스트 |
| `media/` | dev에서 생성되는 실행 중 미디어 파일; Git 제외 |
| `docs/` | 과제 원문과 프로젝트 설계 설명 |
| `openspec/` | 프로젝트 맥락과 change별 계획·진행 상태 |

프로젝트 소유 template와 static은 앱별로 만들지 않고 `src/templates/`와 `src/static/`에 통합합니다. 공개 화면의 공통 layout은 `src/templates/base.html`, 백오피스는 `src/templates/backoffice/base.html`을 사용합니다. 교육 화면은 `src/templates/education/`, 빌드 CSS는 `src/static/css/site.css`에 둡니다. Django의 TEMPLATES DIRS와 STATICFILES_DIRS에 통합 경로를 등록하며, Django admin 등 설치 앱의 자산 탐색은 유지합니다. Tailwind 탐색은 해당 template 경로로 제한하며 규칙·스킬 파일을 탐색하지 않습니다. 이미지 원본은 `presets/education/images/`에 포함하고 실행 시 선택한 media 저장소에 설정합니다.

## JavaScript 진입점과 페이지별 로딩

- `frontend/entries/*.js`는 브라우저가 시작점으로 로드할 파일입니다. 공개 신청은 `application.js`, 교육 admin의 교시 추가는 `education-admin.js`, 백오피스 상세의 이메일 부분 갱신은 `backoffice-detail.js`입니다. 전체 공통·백오피스 공통·다른 페이지의 진입점은 실제 기능이 생길 때 추가합니다.
- 여러 진입점에서 재사용하는 모듈은 필요할 때 `frontend/shared/`에 두고 import합니다. 이 폴더의 모듈은 직접 로드할 진입 파일로 빌드하지 않습니다.
- `npm run build`는 모든 진입점을 함께 빌드합니다. 공개 화면은 필요한 진입 파일을 `type="module"`로 로드합니다. 전체 공통 기능은 `base.html`의 `common_scripts`, 영역 공통 기능은 해당 영역 base template의 `section_scripts`, 페이지 전용 기능은 해당 페이지의 `scripts` 블록에 둡니다. 현재 공통 블록은 비어 있으며 신청 페이지에서 `application.js`를 로드합니다. 백오피스 상세는 이메일 조회 권한이 있을 때만 `backoffice-detail.js`를 로드합니다.
- Django admin은 공개 화면의 base template를 사용하지 않습니다. 교육 커리큘럼 위젯의 `Media.js`가 `education-admin.js`를 admin 폼에 로드합니다. 이 진입점은 외부 모듈 import 없이 실행되는 단일 번들이며 admin의 기본 CSS·JavaScript는 유지합니다.
- Axios 등 라이브러리를 사용하는 진입점만 해당 라이브러리를 import합니다. esbuild는 여러 진입점의 공통 의존성을 `src/static/js/chunks/`에 분리하고 생성된 import로 연결하므로 template에서 chunk 경로를 직접 지정하지 않습니다.

## 기술 선택

- **Python 3.14 / Django 6.1.2**: 기존 호환성 제약이 없는 신규 프로젝트의 기준입니다. Django를 `6.1.2`로 고정하고 lockfile로 정확한 설치 조합을 재현합니다. 장기 운영 시 Django 6.1 지원 종료 전에 업그레이드하며 보안 패치를 계속 확인합니다.
- **DRF**: 과제에서 지정한 API 프레임워크입니다. 공개 교육정보 GET·신청 POST를 제공합니다. 신청 조회·관리는 백오피스와 기본 admin에서 처리하며 별도 관리자 REST API는 제공하지 않습니다. 백오피스 이메일 부분 조회는 Django HTML 응답입니다.
- **PostgreSQL 18.6 / Psycopg 3**: 개발·테스트 DB를 통일합니다. SQLite 대체 경로는 두지 않습니다. `postgres:18.6-bookworm`을 사용하고 volume은 `/var/lib/postgresql`에 마운트합니다.
- **Django Templates / Tailwind CSS / Axios**: 랜딩·교육 상세·신청·백오피스 화면을 단일 서버에서 제공합니다. Tailwind CSS CLI와 esbuild를 `npm run build`로 실행해 CSS와 Axios를 포함한 JS 번들을 생성합니다. 직접 편집하는 소스는 `frontend/`, 배포 산출물은 `src/static/`에 두고 source map·라이선스 고지와 함께 저장소에 포함하며 별도 프론트 서버·SPA·평가 실행 시 Node.js는 요구하지 않습니다. 주소 검색은 Kakao 공식 SDK를 요청할 때만 로딩하고 직접 입력 대안을 유지합니다.
- **Django admin·백오피스**: `/admin/`은 교육·계정·권한·신청·상담·이력·내부 기록을 관리하고 `/backoffice/`는 신청·상담 업무와 이메일 상태 조회를 제공합니다. 인증·세션·모델 권한·저장 서비스를 공유합니다. 신청·상담은 삭제하지 않으며 안내·전송 시도·공유 예산은 조회 전용입니다.
- **django-simple-history 3.13**: 신청 정보·상태·다음 연락 예정의 변경자·시각·전후 값을 보존합니다. 신청에만 적용하며 최초 제출 snapshot은 중복 이력에서 제외합니다. 이력 복원은 제공하지 않습니다.
- **django-environ**: 관리 명령·WSGI·ASGI가 같은 설정 로딩 경로를 사용하도록 Django 설정에서 `.env`를 읽고 boolean·목록을 해석합니다.
- **uv / Ruff / Django test runner**: 런타임 의존성과 개발 의존성을 분리하고, 별도 테스트 프레임워크 없이 필요한 계약을 검증합니다.

교육 소개와 신청은 같은 education 앱에서 제공합니다. API는 `api.py`·`serializers.py`, Q2 진입점과 실행 흐름은 `tasks/` 패키지가 담당합니다. 단순 CRUD에 Service·Repository·Selector 계층을 강제하지 않습니다.

## 백오피스 화면과 저장 경계

`education/backoffice_urls.py`와 `education/backoffice.py`가 전용 URL·화면·이메일 조각 조회를 담당하고 `forms/backoffice.py`가 기존 신청·상담 폼의 날짜 위젯·부모 신청 고정·정정 권한을 조정합니다. `templates/backoffice/base.html`과 navigation·fields include가 공통 틀을 제공하며 목록·상세·로그인은 이를 확장합니다. desktop 사이드바·상단바와 모바일 native 접이식 메뉴는 [Flowbite Admin Dashboard](https://github.com/themesberg/flowbite-admin-dashboard)와 [Tailwind application layouts](https://tailwindcss.com/blog/2024-05-24-catalyst-application-layouts)의 배치 원칙을 참고해 기존 Tailwind로 구성했습니다. 외부 템플릿 패키지는 추가하지 않습니다.

목록·검색·필터는 URL query를 유지하는 일반 GET, 업무 저장은 POST 후 상세 GET redirect입니다. 저장 의도는 `save_application`과 `add_consultation`으로 구분하고 권한을 서버에서 검증합니다. 통합 저장의 `include_consultation` 선택만 상담 검증·저장을 활성화합니다. 안내→신청을 잠근 최신 인스턴스로 폼을 검증하고 기존 저장 서비스와 새 상담을 같은 transaction에 묶습니다. 작성자·부모 신청·상담 당시 일정은 서버가 결정합니다.

`applications/<pk>/email-status/`는 동일한 활성 staff·신청/메일 조회 권한을 검사하는 GET 전용 HTML partial입니다. 상세 최초 표시와 같은 template를 사용하고 Ajax는 이메일 내용만 교체합니다. 미인증은 401, 인가 실패는 403이며 로그인 redirect나 개인정보가 든 오류 응답을 삽입하지 않습니다. 일반 업무 POST의 미인증은 미저장 403 안내를 반환합니다. `CSRF_FAILURE_VIEW`는 백오피스만 전용 안내로 처리하고 공개 화면과 admin은 Django 기본 실패 처리에 위임합니다. 개인정보 전체/부분 응답은 캐시하지 않습니다.

일반 유효성 오류는 입력과 상담 선택을 유지합니다. 저장 중 DatabaseError는 transaction 밖에서 처리하여 예외 원문·POST 개인정보를 포함하지 않는 전용 500 안내를 반환합니다. 성공 시 redirect는 새로고침 재제출을 막지만 모든 POST의 중복 방지나 낙관적 동시 편집 감지는 제공하지 않습니다. 로그인·저장 오류 후의 확인 절차는 [운영 가이드](guides/operations.md#백오피스-계정과-요청-처리)를 따릅니다.

## 백그라운드 task 구성

함수 분리의 공통 판단 기준은 [함수 분리와 실행 흐름의 가독성](development.md#함수-분리와-실행-흐름의-가독성)을 따릅니다. task에는 다음 배치·의존성 규칙을 적용합니다.

- `tasks/reminders.py`에는 상담 안내 등록·발송 진입점과 실행 흐름을, `tasks/media.py`에는 이미지 정리 task를 둡니다.
- 긴 이메일 처리의 내부 단계는 같은 패키지의 `reminder_dispatch.py`·`reminder_delivery.py`로 분리하며 짧은 task는 자체 구현을 유지합니다.
- `tasks/__init__.py`는 세 task 함수를 공개해 기존 `education.tasks.<함수명>` 경로를 유지합니다. 지원 모듈은 공개 패키지를 역으로 import하지 않고 필요한 하위 모듈을 직접 참조합니다. import 시 작업 등록·외부 호출은 수행하지 않습니다.
- task 경로를 변경할 때는 생산 코드뿐 아니라 영속 스케줄·대기 작업·실패 작업 재등록에 미치는 영향도 확인합니다. 적용 중인 큐 시스템에 맞는 전환 절차와 검증을 포함합니다.

현재 `tasks/reminder_dispatch.py`는 상담 안내 이메일의 오래된 상태 복구·대상 잠금·배치 등록을, `tasks/reminder_delivery.py`는 전송 처리권·공유 예산·결과 기록·메일 생성·SES 오류 분류를 담당합니다. 공유 안전 예외는 `tasks/exceptions.py`에 둡니다.

## 환경과 패키지 관리

uv는 `[tool.uv] package = false`인 비패키지 방식으로 사용합니다. 애플리케이션 자체를 빌드·설치할 필요가 없으므로 `[build-system]`을 두지 않습니다. 배포용 Python 라이브러리의 build backend 규칙과 구분합니다.

공통 실행 의존성은 Django, DRF, `psycopg[binary]`, `django-environ`, `django-q2`, `django-simple-history`입니다. `prod` 그룹에는 `django-storages[s3]`와 `django-ses`(events extra 제외), 기본 `dev` 그룹에는 `prod` 포함과 Ruff를 둡니다. local 그룹이나 별도 AWS extra는 만들지 않습니다. 로컬은 `uv sync --locked`, 운영은 `uv sync --locked --no-default-groups --group prod`로 설치합니다. 운영 설치 뒤 직접 가상환경 실행 또는 `uv run --no-sync`를 사용하며 `uv.lock`을 함께 관리합니다. 개발에서 AWS backend를 선택하거나 자격 증명을 조회하지 않습니다.

새 Django 프로젝트와 앱의 기본 골격은 LLM이 직접 작성하지 않고 Django의 `startproject`·`startapp` 명령으로 생성한 뒤 필요한 설정을 편집합니다. Django 기본 인증·admin·CSRF middleware를 유지합니다. 테스트는 앱의 `tests/` 패키지에 두며 같은 앱에 `tests.py`를 함께 두지 않습니다.

설정은 `src/config/settings/base.py`(공통), `dev.py`(로컬 미디어), `prod.py`(S3·CloudFront)로 분리합니다. manage.py·ASGI·WSGI의 기본은 `config.settings.dev`이며 프로세스에 지정한 `DJANGO_SETTINGS_MODULE`을 보존합니다. 운영은 `config.settings.prod`를 프로세스 환경이나 관리 명령의 `--settings`로 명시합니다. `.env`를 읽기 전에 모듈이 선택되므로 `.env`에 설정 모듈을 적어 자동 전환하지 않습니다. Django 설정은 django-environ으로 저장소 루트의 `.env`를 자동 로딩하며, 이미 주입된 환경 변수를 우선한다. `.env`가 없어도 필요한 환경 변수를 직접 주입하면 실행할 수 있습니다. uv의 `--env-file`은 중복 사용하지 않습니다. secret key, DB 이름·사용자·비밀번호가 없거나 비어 있으면 값 노출 없이 설정 오류로 중단합니다. DEBUG 기본값은 false이며 django-environ의 boolean 해석을 따릅니다(`true`/`1`/`yes`/`on`/`y`/`ok`는 true, 대소문자와 앞뒤 공백 무시). 허용 host는 목록으로 읽은 뒤 각 항목의 공백과 빈 항목을 제거합니다. 로컬 예제는 DEBUG=true와 loopback host를 사용합니다. 언어는 한국어, 시간대는 `Asia/Seoul`, timezone-aware datetime을 사용합니다.

미디어 이미지는 FileField의 저장소 상대 이름으로 참조하고 template는 `.url`을 사용합니다. dev는 저장소 루트 `media/`와 `/media/`를 사용하고 DEBUG일 때만 Django가 제공합니다. dev에서는 AWS 백엔드를 로딩하거나 자격 증명을 조회하지 않습니다. prod는 비공개 S3에 `media/` prefix로 저장하고 CloudFront HTTPS URL로 공개 교육 이미지를 제공합니다. CloudFront OAC·버킷·IAM은 배포 환경에서 사전에 준비합니다. 운영은 DEBUG 활성화와 필수 host·버킷·리전·CloudFront 도메인 누락을 거부하며 로컬로 fallback하지 않습니다. IAM role과 SDK 기본 credential chain을 사용합니다. static CSS와 media의 책임은 분리하며 운영 static 배포는 별도 범위입니다.

Compose는 개발용 DB만 실행하고 포트를 loopback에만 공개합니다. 로컬 계정은 테스트 DB 생성 권한이 있으며 운영에 재사용하지 않습니다. named volume과 실제 `.env`를 보호하고 정지 시 volume을 삭제하지 않습니다.

개발·검증·Git 정책은 [개발 규약](development.md)을 따릅니다. 전체 문서의 역할은 [문서 안내](README.md)를 참고하세요.

## 교육 데이터와 프리셋

Education은 교육명·소개·미디어 FileField·목표·대상·시수별 커리큘럼과 운영 정보를 보관합니다. `operation_type`은 `instructor_led`(코치 출강) 또는 `courseware`(코스웨어), `operation_note`는 선택적인 일반 텍스트 진행 안내, `is_accepting_inquiries`는 상담 접수 활성 여부입니다. 운영 방식·진행 안내·접수 활성의 모델 기본값은 코치 출강·빈 문자열·활성이며 접수 중단도 소개를 숨기지는 않습니다. 지역·일정·인원은 협의 안내로 제공하고 기수·반·좌석 모델은 두지 않습니다.

목표·대상과 커리큘럼은 JSONField를 사용하며 `education/validators.py`의 공통 field validator가 `full_clean()`에서 구조와 교시 순서를 검증합니다. `seed_educations`도 이 검증을 호출합니다. `save()`·`QuerySet.update()`·`bulk_create()`는 입력 검증을 자동 실행하지 않습니다. 기본 admin의 `EducationForm`은 목표·대상을 줄 단위 텍스트로 받고 커리큘럼은 총 차시 수·교시·주제·활동·설명을 입력하는 formset으로 편집합니다. 교시 추가·삭제와 오류 시 입력 보존을 지원하며 저장 전에 같은 공통 validator를 적용합니다. 관리자는 JSON 문법을 입력하지 않습니다. 신청 입력은 별도 serializer로 검증하고 신규 접수 시 교육 row lock 아래 접수 활성 여부를 확인합니다.

프리셋 JSON과 이미지 원본은 앱의 실행 코드와 분리해 저장소 루트 `presets/education/`에 보관합니다. 초기화 명령은 `src/education/management/commands/`에 유지하고 Django `BASE_DIR`의 상위인 저장소 루트를 기준으로 프리셋을 찾습니다. 초기화를 실행할 배포물에도 이 폴더를 포함해야 합니다. 프리셋 원본은 Git으로 관리하며 직접 제공하는 static이나 실행 중 업로드 저장소로 사용하지 않습니다. `seed_educations`는 사전 검증 후 누락 교육만 추가하고 기존 교육의 운영 정보와 이미지를 보존합니다. source_url·source_image_url·collected_on·editorial_note는 프리셋 JSON에만 보관하고 초기화 시 DB 저장 대상에서 제외합니다. 신규 프리셋의 진행 안내는 과제용 정책임을 JSON의 편집 설명에 명시하며 상세 화면에는 수집 기록을 표시하지 않습니다. 저장소가 반환한 실제 이름을 DB에 기록합니다. DB 오류 시 transaction은 롤백되지만 파일은 남을 수 있으므로 자동 삭제하지 않고 재실행에서 재사용합니다.

`application_presets.json`은 선택 생성할 가상 신청 32개의 고정 제출 UUID·교육 slug·개인정보·상태·상대 날짜·상담·모의 이메일 사례를 정의합니다. `seed_educations --with-applications --staff-user <기존 사용자명>`은 개발 설정·simulated·locmem 환경에서만 기존 활성 staff를 상담 작성자로 연결합니다. Django timezone으로 한 번 얻은 한국 시각과 python-dateutil의 relativedelta로 최초 날짜를 계산합니다. python-dateutil은 기존 잠금 버전을 유지한 공통 직접 의존성입니다. 전용 날짜 엔진이나 별도 모델 필드는 두지 않습니다.

과거 신청 샘플의 최초 생성은 command가 모델 검증·일반 save로 수행하고 현재 시각 기준의 공개 API·업무 변경 서비스를 완화하지 않습니다. 초기 history는 시스템 작성자·샘플 사유·접수 시각을 기록하며 가짜 담당자 상태 전이 이력을 만들지 않습니다. 고정 request_id가 존재하면 불변 최초 이메일·교육 slug의 충돌만 확인한 뒤 신청과 종속 기록을 통째로 보존합니다. 새 신청·상담·안내·시도·이력과 새 교육은 한 transaction에서 저장하고 실패하면 모두 rollback합니다. 신규 교육 이미지는 Storage 반환 키를 최초 DB 저장에 사용하여 이미지 정리 큐도 만들지 않습니다. 상세 운영 경계와 합성 메일 상태는 [개발용 신청 샘플](guides/operations.md#개발용-신청-샘플)을 따릅니다.

신규 교육 이미지의 저장 키는 `education/<media_id의 32자 hex>/images/<filename>`입니다. `media_id`는 `UUIDField(default=uuid7, unique=True, editable=False)`로 생성 전에 부여하며 교육 생성 후 변경하지 않습니다. 기존 숫자 PK와 상세 URL의 slug는 유지합니다. UUIDv7은 Django의 Python 기본값으로 생성하며 DB 기본값은 두지 않습니다. 프리셋에는 교육별 고정 UUIDv7을 기록하고 형식·버전·중복을 쓰기 전에 검증합니다. 일반 FileField 파일 저장은 `education/media.py`의 upload_to callable에서 UUID 파일명과 원본 확장자를 사용합니다. 프리셋은 실패 후 재사용할 수 있도록 SHA256 내용 해시와 `.png`를 사용합니다. 로컬·S3 모두 덮어쓰기를 허용하지 않습니다. 기존 `education/presets/` 등의 키는 자동 이동하지 않으며 slug만 바꿔도 기존 파일 키는 유지합니다. 경로 함수는 migration에서도 참조하므로 import 경로를 유지합니다. 프로젝트 schema는 전체 모델을 담은 단일 `src/education/migrations/0001_initial.py`로 빈 DB에 생성합니다. 이전 개발 migration 이력은 사용자 요청으로 통합했으며 기존 DB에 적용하는 업그레이드 경로는 제공하지 않습니다. 마이그레이션 정리 기준은 [개발 규약](development.md#마이그레이션-변경과-이력-정리)을 따릅니다.

교육 단일·일괄 삭제와 일반 `save()`의 이미지 교체는 `education/signals.py`에서 이전 키를 수집하고 같은 DB transaction 안에 Q2 ORM 작업을 기록합니다. 일반 save는 post_save까지 atomic 경계에 포함하며 삭제는 Django의 deletion transaction을 사용합니다. commit 후 worker가 default Storage와 같은 DB alias에서 참조를 재확인해 미참조 파일만 삭제하므로 rollback·공유·재연결 파일을 보존합니다. 같은 키·image 제외 저장은 정리하지 않으며 `QuerySet.update()`·`bulk_update()`·직접 SQL은 signal을 우회합니다.

큐 등록 실패는 교육 DB 변경도 rollback합니다. commit 후 저장소 삭제 실패는 DB 변경을 유지하고 안전한 키·예외 종류로 Q2의 제한 재시도를 사용하며 총 3회 후 실패를 보존합니다. 재등록 시에도 현재 참조를 검사합니다. S3 I/O는 연결 5초·읽기 15초와 단일 SDK 호출로 task timeout보다 짧게 제한합니다. 저장 후 DB rollback·프로세스 중단의 고아 파일 전수 청소와 별도 DLQ는 제공하지 않습니다. 프리셋 실패 파일은 재실행으로 재사용하고 원본은 청소하지 않습니다. 기본 검증은 임시 로컬 Storage·테스트 DB에서 수행합니다.

## 신청과 자동 안내의 경계

| 모델 | 책임 |
| --- | --- |
| `Education` | 교육 소개·커리큘럼·이미지·상담 접수 가능 여부 |
| `EducationApplication` | 최초 제출 원본·현재 신청 정보·상담 진행 상태·다음 연락 예정 |
| `ConsultationRecord` | 작성자·시각·당시 일정이 포함된 상담 및 정정 기록 누적 |
| `HistoricalEducationApplication` | django-simple-history가 생성하는 신청 변경 이력 |
| `EducationApplicationReminderEmail` | 신청별 안내 이메일 대상 시각·현재 처리 상태·최근 전송 증거 |
| `MailAttempt` | 처리권을 확보한 개별 전송 시도의 시작·종료·결과 |
| `MailSendBudget` | SES worker들이 공유하는 다음 발송 허용 시각 |

신청 관련 schema는 신청·안내·전송 시도·공유 발송 예산을 각각 저장하고 무결성을 위한 제약·인덱스를 둡니다. 최초 제출 원본과 현재 관리값을 구분하고 안내의 전송 증거를 별도로 보존합니다.

`EducationApplication`은 request_id의 DB unique 제약과 교육 row lock으로 동일 제출을 재사용하며 신청 당시 slug·교육명 snapshot과 개인정보를 보관합니다. 교육 삭제는 SET_NULL이며 신청·안내를 지우지 않습니다. 공개 API는 교육 GET과 CSRF를 검사하는 익명 신청 POST만 제공하고 응답은 request_id·접수 상태로 제한합니다. 교육의 접수 중단·삭제·날짜 경과 전후에도 기존 제출 확인은 새 접수 검증과 구분합니다.

교육 신청 모델은 `EducationApplication`, 해당 안내 이메일은 `EducationApplicationReminderEmail`로 명명합니다. 관계명 `EducationApplication.notification`·`MailAttempt.notification`과 기존 task 경로는 유지합니다. DB 테이블과 history 모델은 Django가 새 모델명으로 생성합니다.

신청과 OneToOne 안내는 같은 transaction에 저장합니다. 단일 Q2 기본 큐·qcluster·worker 2개에서 처리하고 대상 등록 스케줄은 명시적 준비 명령으로만 만듭니다. 처리권·MailAttempt·시도 횟수를 먼저 commit한 뒤 긴 외부 호출을 수행하고 결과는 현재 attempt_id와 상태가 일치할 때 함께 저장합니다. 수신자·본문은 Q2 payload에 넣지 않고 ID로 조회합니다. SES 전송 예산은 별도 singleton row의 짧은 lock으로 worker 간 공유합니다. 상세 정책과 명령은 [운영 가이드](guides/operations.md#백그라운드-worker와-자동-안내)를 따릅니다.

실제 전송은 Django 이메일 API와 `MAILERS["default"]["BACKEND"]` 설정을 따르며 개발 locmem·운영 django-ses를 선택합니다. 안내에 저장한 mode는 생성 당시 환경을 기록하고 환경 불일치 발송을 차단하는 값이며 backend를 선택하지 않습니다. 모의 완료와 SES 접수를 구분하고 결과 불명은 재전송하지 않습니다. SNS·SQS·웹훅·실제 전달·반송 추적은 현재 구성에 포함하지 않습니다. 개인정보와 상담 기록은 백오피스와 admin 모두 Django 모델 권한으로 제한하며 공개 신청 조회는 제공하지 않습니다.

## 신청 관리와 이력

`EducationApplication`은 수정 가능한 관리값과 최초 정규화 제출 JSON snapshot을 분리합니다. 원본은 관리자에게 읽기 전용이고 공개 재시도는 원본만 비교합니다. 상담 진행 상태가 바뀌어도 공개 응답은 최초 접수만 확인합니다. 원본 snapshot은 history에서 제외하고 신청의 일반 save는 history와 같은 transaction에 저장합니다.

`forms/education.py`·`forms/application.py`·`forms/consultation.py`는 입력 표시와 폼 검증을 담당합니다. 신청 변경의 공통 검증·저장은 `services/applications.py`에 두며 별도 service 클래스나 재노출 wrapper는 만들지 않습니다. worker와 관리 저장이 공유하는 종료 상태는 `EducationApplication.TERMINAL_STATUSES`를 사용합니다.

관리 변경은 `services.applications.save_application`을 사용합니다. 안내→신청 row lock 순서로 worker claim과 직렬화하며 신청·이력·안내 조정을 함께 저장합니다. admin은 폼 조회 전 같은 lock을 얻고 상담 inline도 요청 transaction에 포함합니다. 백오피스도 같은 lock 순서와 저장 서비스를 사용하고 선택한 상담을 함께 저장합니다. 다음 연락 예정은 follow_up에서만 사용하며 메일 대상 시각과 구분합니다.

ConsultationRecord는 작성자·시각·결과·내용·당시 일정과 정정 대상 원기록을 누적합니다. 기존 기록은 수정·삭제하지 않고 같은 신청의 원기록을 가리키는 정정으로 보완합니다. 신청·상담의 instance/QuerySet 삭제와 상담 update를 차단하며 상담 작성자가 있는 계정은 삭제 대신 비활성화합니다.

신청 이력은 django-simple-history로 기록하고 admin에서 읽기만 허용합니다. 교육 삭제로 인한 연결 해제는 pre_delete에서 이력 지원 save를 사용합니다. QuerySet.update·bulk_update·직접 SQL은 일반 이력 포착 경로가 아니므로 새 관리 코드에서 사용하지 않습니다. 직접 SQL의 변조 방지나 운영 개인정보 삭제 정책까지 보장하지 않습니다.
