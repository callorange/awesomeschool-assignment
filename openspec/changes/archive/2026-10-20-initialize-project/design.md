# Design

## Context

동기는 [proposal.md](proposal.md)의 Why를 따른다. 현재 저장소에는 과제 원문, `.gitignore`, OpenSpec과 에이전트 도구 설정이 있으며 애플리케이션 코드·의존성 manifest·실행 가능한 테스트·기존 capability spec은 없다. 로컬에서 uv, Python, Docker 실행 파일은 확인했지만 Docker daemon과 PostgreSQL 연결은 아직 검증하지 않았다.

과제는 Django·PostgreSQL·DRF를 지정한다. 우대 항목은 MVP 이후로 유지한다는 사용자 결정을 반영한다. 이번 change는 그 기능을 구현하기 전의 초기 구성이므로 `skip_specs: true`이며 기능 spec을 만들지 않는다.

## Goals / Non-Goals

**Goals:**

- 신규 checkout에서 문서화된 절차로 의존성 설치, 로컬 DB 기동, Django 내장 migration, system check와 테스트를 실행할 수 있게 한다.
- 교육·신청 기능을 이어서 구현할 앱 위치와 화면 기술을 정하고, 필요한 최소 의존성을 고정한다.
- 사람이 읽는 개발 규약과 OpenSpec에 전달할 지침의 책임을 구분한다.

**Non-Goals:**

- 교육·신청 모델, 랜딩 페이지, 신청 폼, 업무 API, 신청 CRUD 및 별도 관리자 화면 구현.
- 신규 인증 방식, 사용자 회원가입, Service·Repository·Selector 계층 도입.
- 자동 메일, Spreadsheet, AWS 리소스·배포, AI 사용 기록 기능의 구현 및 관련 패키지 설치.
- 애플리케이션 컨테이너 이미지, 운영 서버, CI 파이프라인 구성. Compose는 로컬 DB 실행에만 사용한다.

## Decisions

### 1. 단일 Django 애플리케이션과 최소 의존성

Python 3.14와 Django 6.1.2를 사용한다. `.python-version`은 `3.14`, `pyproject.toml`의 Python 지원 범위는 `>=3.14,<3.15`, Django 의존성은 `Django==6.1.2`로 명시한다. DRF와 Psycopg는 각각 3.x 계열 중 Python 3.14·Django 6.1.2와 호환되는 안정 버전을 선택한다. 구현 시 공식 호환성 정보와 의존성 resolution으로 조합을 검증하고 정확한 설치 버전을 `uv.lock`에 기록한다.

기존 애플리케이션이나 오래된 패키지와의 호환성 제약이 없는 신규 프로젝트이므로, 사용자가 선택한 Python 3.14·Django 6.1.2 조합을 기준으로 시작한다. 대안인 Django 5.2 LTS보다 지원 기간은 짧지만 최신 안정 계열의 admin 개선과 내장 template partials 등을 후속 기능에서 필요에 따라 활용할 수 있다. 버전 선택을 이유로 이번 초기 구성에 새 기능을 추가하지 않는다.

| 분류 | 직접 의존성 / 도구 | 용도 |
| --- | --- | --- |
| 런타임 | `Django` | ORM, template, admin, 기본 인증과 테스트 기반 |
| 런타임 | `djangorestframework` | 후속 신청 API와 API 테스트 도구 |
| 런타임 | `psycopg[binary]` | 로컬 PostgreSQL 연결, 별도 드라이버 컴파일 회피 |
| 런타임 | `django-environ` | 저장소 루트 `.env` 로딩과 환경 변수 boolean·목록 해석 |
| 개발 | `ruff` | Python lint와 format 검사 |
| 환경 관리 | uv | 의존성 설치 및 lockfile 관리 |
| 테스트 | Django TestCase / DRF APITestCase | 별도 테스트 패키지 없이 초기 및 후속 검증 |

uv는 비패키지 방식으로 애플리케이션의 의존성과 실행 환경을 관리한다. `pyproject.toml`에 `[tool.uv]`의 `package = false`를 명시하고 프로젝트 자체를 빌드·설치하기 위한 `[build-system]`과 배포용 패키지는 추가하지 않는다. 이 애플리케이션의 비패키지 실행 방식을 Project Rules에도 명시하여 배포 패키지용 build backend 규칙과 구분한다. 런타임과 개발 의존성을 분리하고 `.python-version`, `pyproject.toml`, `uv.lock`을 함께 관리한다. README의 설치 명령은 `uv sync --locked`로 통일한다.

대안인 별도 React 프론트엔드는 빌드·배포 및 API 연동 구성을 늘린다. 이번 과제의 핵심 흐름에는 Django Templates, CSS, 브라우저 기본 `fetch`가 충분하므로 별도 Node 도구를 추가하지 않는다. Pillow는 이미지 업로드 요구가 생길 때, 메일·Google 연동 패키지는 해당 후속 기능을 구현할 때 검토한다.

### 2. src 구조와 단일 education 앱

| 경로 | 책임 |
| --- | --- |
| `src/manage.py` | Django 관리 명령 진입점 |
| `src/config/` | settings, 프로젝트 URL, ASGI·WSGI 진입점 |
| `src/education/` | 후속 교육 소개·신청 기능의 앱 골격 |
| `src/education/migrations/` | 후속 업무 migration 위치 |
| `src/education/tests/` | 초기 smoke test와 후속 업무 테스트 |
| `src/education/templates/education/` | 후속 화면 구현 시 생성할 template 위치 |
| `src/education/static/education/` | 후속 화면 구현 시 생성할 CSS·JavaScript·정적 이미지 위치 |
| `docs/architecture.md` | 구조, 기술 선택 이유, 개발 규약 |
| `README.md` | 실행·검증 절차, 현재 구현 상태, 전체 MVP와 후속 작업 목록 |

프로젝트와 앱의 기본 골격은 LLM이 파일을 직접 작성하지 않고, 설치된 Django의 기본 template을 사용하는 `startproject`와 `startapp` 명령으로 생성한다. 의존성 설치 후 저장소 루트에서 대상 디렉터리를 준비하고 다음 순서로 실행한다.

```powershell
New-Item -ItemType Directory src
uv run django-admin startproject config src

New-Item -ItemType Directory src/education
uv run django-admin startapp education src/education
```

생성 후 `INSTALLED_APPS`에 `education`의 `AppConfig`와 `rest_framework`를 등록하고 환경 변수·PostgreSQL 등 프로젝트에 필요한 설정만 편집한다. 환경 변수와 PostgreSQL 및 앱 설정을 모두 적용한 뒤 `manage.py check`를 실행하며 생성 직후의 기본 SQLite 설정을 검증 완료 근거로 삼지 않는다. `manage.py`, ASGI·WSGI 진입점, `AppConfig`, 기본 migration 패키지 등 Django가 제공하는 골격을 수작업으로 재작성하지 않는다. 생성된 `tests.py`는 테스트를 추가하는 단계에서 `tests/__init__.py`와 테스트 모듈로 전환하고, 기존 테스트를 보존하며 같은 앱에 `tests.py`와 `tests/`가 공존하지 않게 한다.

설정은 `settings.py` 하나에서 시작하고 환경별 값만 환경 변수로 주입한다. education 앱은 등록하되 업무 모델·API·페이지를 미리 만들지 않는다. 명령으로 생성된 기본 `models.py`는 업무 모델 구현으로 간주하지 않는다. 빈 template·static 폴더나 미래 연동 패키지도 만들지 않는다. Django 기본 admin URL과 기본 인증 앱은 활성화한다.

교육과 신청을 별도 앱으로 나누는 대안은 현재 규모에서 앱 간 연결을 늘린다. 하나의 앱에 두고 실제 책임이 분리될 때 재검토한다. 동일 이유로 Service·Selector 계층과 환경별 settings 분리는 도입하지 않는다.

### 3. PostgreSQL과 명시적인 환경 변수

개발·테스트 DB는 모두 PostgreSQL 18.6으로 맞추고, `compose.yaml`의 이미지는 `postgres:18.6-bookworm`으로 명시한다. 기존 데이터나 확장 모듈에 묶인 제약이 없는 신규 프로젝트이므로 Django 6.1과 호환되고 17 계열보다 지원 기간이 긴 18 계열을 선택한다. `latest` 태그를 사용하지 않으며 후속 패치 적용 시 이미지 태그를 갱신하고 관련 검증을 실행한다.

`compose.yaml`은 PostgreSQL 서비스, `pg_isready` healthcheck, named volume을 제공하며 DB 포트는 로컬 loopback에만 바인딩한다. PostgreSQL 18 공식 이미지의 volume 마운트 대상은 `/var/lib/postgresql`이고, 기본 `PGDATA`는 `/var/lib/postgresql/18/docker`다. 17 이하의 `/var/lib/postgresql/data` 마운트 관례를 재사용하지 않는다. 이미 사용 중인 포트는 `POSTGRES_PORT`로 변경할 수 있게 한다. 이 구성은 로컬 개발 전용이다.

`.env.example`은 다음 환경 변수와 개발용 예시를 문서화한다. 실제 비밀값은 저장하거나 출력하지 않는다.

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`

Compose와 호스트에서 실행하는 Django가 같은 DB 이름·사용자·포트를 사용한다. Django의 host 기본값은 로컬 연결을 기준으로 한다. Django 설정은 django-environ으로 저장소 루트의 `.env`를 자동 로딩하며, 이미 주입된 환경 변수를 우선한다. `.env`가 없어도 필요한 환경 변수를 직접 주입하면 실행할 수 있다. uv의 `--env-file`은 중복 사용하지 않는다. `DJANGO_DEBUG`는 django-environ의 boolean 해석을 사용하고 기본값은 false로 둔다. secret key와 DB 이름·사용자·비밀번호는 없거나 비어 있으면 실제 값을 출력하지 않는 설정 오류로 종료한다. 기존 `POSTGRES_*` 계약을 유지하며 `DATABASE_URL`로 변경하지 않는다. 언어는 한국어, 시간대는 `Asia/Seoul`, timezone-aware datetime을 사용한다.

`.env.example`에는 로컬 개발용 `DJANGO_DEBUG=true`, `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`, `POSTGRES_HOST=127.0.0.1` 예시를 제공한다. 허용 host는 쉼표로 분리해 Django 설정의 목록으로 변환한다. DEBUG의 예시값은 로컬 개발용이며 환경 변수 누락 시의 false 기본값은 유지한다. README에는 예제 복사 후 개발용 secret key와 DB 비밀번호를 준비하는 절차를 포함한다.

PostgreSQL 대신 SQLite를 개발용으로 쓰는 대안은 DB 차이를 숨기므로 채택하지 않는다. 개발 DB 사용자는 Django 테스트 DB를 생성할 권한이 있어야 하며 실제 공유·운영 DB에 이 계정을 재사용하지 않는다.

### 4. 거버넌스의 원본과 전달 경로 분리

- 과제 원문은 `docs/awesomeschool-assignment.md`를 유지한다.
- `docs/architecture.md`에는 선택한 구조·스택·검증 방법과 그 이유를 기록한다. README에서 연결하고 동일 내용을 여러 파일에 장문으로 반복하지 않는다.
- `AGENTS.md`는 기존 managed block과 GitNexus 구역을 보존하고 Project Rules에 프로젝트 위치·문서 참조·검증 명령만 보충한다. 이 파일은 `.git/info/exclude`로 제외된 로컬 지침이므로 유일한 공유 규약으로 삼지 않으며 추적 상태를 변경하지 않는다.
- `openspec/config.yaml`은 `schema: spec-driven`과 기존 문서 언어 정책을 유지한다. context에 프로젝트 목적·확정 스택·MVP 경계·규약 문서 참조를 간결하게 추가한다. rules에는 proposal의 범위 구분, design의 관련 데이터·권한 영향 설명, tasks의 관찰 가능한 검증 포함 기준을 해당 artifact id별로 둔다. operations.apply에는 관련 검사 결과를 확인한 뒤 완료 처리하도록 하는 지침을 둔다. custom schema나 별도 constitution은 추가하지 않는다.
- README에는 초기 구성 완료와 전체 MVP 완료를 구분한다. MVP 기능 목록은 교육 소개, 반응형 신청 폼과 비동기 제출, Django admin CRUD·상태 관리, DRF GET/POST API로 정리한다. 후속 API의 기본 방향은 익명 신청 생성과 관리자 전용 개인정보 조회이며, 실제 계약은 기능 change에서 정의한다.
- 별도 관리자 목록 화면, Spreadsheet 내보내기, AWS 계획·배포, AI 활용 기록은 README의 MVP 이후 예정 목록에 유지한다. 자동 안내 메일은 우대 항목과 구분하여 MVP 포함 여부가 미결정인 선택 기능으로 기록한다.

### 5. 검증과 완료 조건

README에 다음 명령과 실행 순서를 제공한다. `.env` 준비와 Docker 실행을 선행 조건으로 명시한다.

```text
uv sync --locked
docker compose config --quiet
docker compose up -d --wait db
uv run python src/manage.py check
uv run python src/manage.py migrate --noinput
uv run python src/manage.py makemigrations --check --dry-run
uv run python src/manage.py test education
uv run ruff check .
uv run ruff format --check .
```

Ruff의 `target-version`은 `py314`로 설정하며 template managed 파일, 도구 설치 파일과 생성 캐시를 검사·자동 수정하지 않도록 검사 범위를 프로젝트 소유 Python 코드로 제한한다.

초기 테스트는 설정과 DB의 연결을 실제 PostgreSQL 경로로 검증하는 작은 smoke test로 구성한다. 기본 DB 연결의 vendor가 PostgreSQL인지와 간단한 쿼리 결과를 확인하고, `/admin/login/`에 접근했을 때 로그인 화면이 정상 응답하는지 확인한다. 실제 `.env`와 격리된 임시 디렉터리에 설정 파일을 복사하여 루트 `.env` 로딩, 기존 환경 변수의 우선순위, DEBUG boolean과 허용 host 목록 해석, 필수 환경 변수 누락·빈 값의 오류를 검증한다. 빈 환경 변수도 `.env` 값으로 덮어쓰지 않는다. 이 단계에 존재하지 않는 업무 동작의 가상 테스트나 외부 서비스 연결 테스트는 만들지 않는다.

`migrate` 및 테스트를 통과하면 PostgreSQL 연결과 내장 인증·admin 테이블 초기화를 확인할 수 있다. 명령 실행 실패는 코드 오류와 Docker·DB·권한 등 환경 문제를 구분해 기록하며, 검증하지 못한 항목을 완료로 표시하지 않는다.

로컬 관리자 화면은 README에 기재한 `runserver` 명령으로 확인한다. 로컬 `.env`의 DEBUG 설정과 Django 기본 `staticfiles` 구성을 사용하여 `/admin/login/`뿐 아니라 화면에서 참조하는 admin CSS 요청도 HTTP 200으로 응답하고 스타일이 적용되는지 확인한다. 테스트 클라이언트의 로그인 페이지 HTTP 200 결과만으로 정적 파일 표시까지 검증했다고 간주하지 않는다. 운영 정적 파일 배포 구성은 이번 범위에 추가하지 않는다.

## Risks / Trade-offs

- [Docker 실행 파일만 확인했고 daemon 상태는 미검증] → apply에서 daemon과 Compose를 확인하고 실패 원인을 환경 문제로 보고한다. SQLite로 자동 대체하지 않는다.
- [로컬 DB 자격 증명과 데이터가 생성됨] → 로컬 개발에만 사용하고 loopback 바인딩, `.env` 제외, named volume으로 관리한다. 예시 파일에는 실제 비밀값을 넣지 않는다.
- [PostgreSQL 테스트에 별도 DB 생성 권한이 필요함] → 로컬 Compose 계정으로 검증하고 해당 전제와 테스트 DB 분리를 README에 기록한다.
- [AGENTS.md는 다른 checkout에 전달되지 않음] → 공유할 규약은 versioned 문서와 OpenSpec 설정에도 반영한다.
- [Django 6.1은 LTS가 아니며 지원 종료가 2027년 12월로 예정됨] → 장기 운영 시 지원 종료 전에 지원되는 Django 계열로 업그레이드한다. `6.1.2` 고정은 보안 업데이트를 생략한다는 뜻이 아니며, 후속 패치 적용 시 의존성 선언과 lockfile을 함께 갱신하고 관련 검증을 실행한다.
- [초기 구성과 MVP 완성을 혼동할 수 있음] → README와 후속 작업 목록에서 기능 미구현 상태를 명시한다.

## Migration Plan

1. 의존성 manifest와 lockfile을 준비하고 Django의 `startproject`·`startapp` 명령으로 프로젝트·앱 골격을 생성한 뒤 필요한 설정을 적용한다.
2. 환경 변수 예제와 로컬 DB Compose를 추가하고 새 로컬 DB에 Django 내장 migration을 적용한다. 업무 모델 migration은 생성하지 않는다.
3. smoke test와 정적 검사를 실행하고 재현 가능한 절차를 문서화한다.
4. Project Rules와 OpenSpec 설정을 동기화한다.

기존 운영 데이터 변환이나 배포는 없다. 되돌릴 때는 이번 변경의 프로젝트 파일만 되돌리고 필요하면 `docker compose down`으로 컨테이너를 중지한다. DB volume은 보존하며 `down -v` 또는 데이터 삭제는 실행하지 않는다. Git commit·push는 이번 change의 실행 작업에 포함하지 않는다.
