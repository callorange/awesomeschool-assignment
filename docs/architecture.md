# 아키텍처와 개발 규약

교육 소개 → 신청 접수 → 신청 관리라는 하나의 흐름을 단일 Django 프로젝트에서 구현합니다. 초기 구성에서는 개발 환경과 앱 골격만 제공하며, 실제 교육·신청 기능은 후속 change에서 추가합니다. 실행 명령과 구현 예정 목록은 [README](../README.md), 원래 요구사항은 [과제 문서](awesomeschool-assignment.md)를 기준으로 합니다.

## 프로젝트 구조

| 경로 | 책임 |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.python-version` | Python·의존성·개발 도구와 실행 환경 |
| `compose.yaml`, `.env.example` | 로컬 PostgreSQL과 환경 변수 계약 |
| `src/manage.py` | Django 관리 명령 진입점 |
| `src/config/` | 설정·URL·ASGI·WSGI 진입점 |
| `src/education/` | 향후 교육 소개와 신청 기능을 담을 앱 |
| `src/education/migrations/` | 업무 migration 위치; 현재는 업무 migration 없음 |
| `src/education/tests/` | 설정 테스트와 PostgreSQL·관리자 화면 smoke test |
| `docs/` | 과제 원문과 프로젝트 설계 설명 |
| `openspec/` | 프로젝트 맥락과 change별 계획·진행 상태 |

화면 구현 시 앱 안의 `templates/education/`와 `static/education/`를 생성합니다. 초기 구성에 빈 화면·정적 파일 폴더를 미리 추가하지 않습니다.

## 기술 선택

- **Python 3.14 / Django 6.1.2**: 기존 호환성 제약이 없는 신규 프로젝트의 기준입니다. Django를 `6.1.2`로 고정하고 lockfile로 정확한 설치 조합을 재현합니다. 장기 운영 시 Django 6.1 지원 종료 전에 업그레이드하며 보안 패치를 계속 확인합니다.
- **DRF**: 과제에서 지정한 API 프레임워크입니다. 설치·앱 등록은 끝났으며 신청 API는 후속 구현입니다.
- **PostgreSQL 18.6 / Psycopg 3**: 개발·테스트 DB를 통일합니다. SQLite 대체 경로는 두지 않습니다. `postgres:18.6-bookworm`을 사용하고 volume은 `/var/lib/postgresql`에 마운트합니다.
- **Django Templates / CSS / `fetch`**: 랜딩·신청 화면과 비동기 처리를 하나의 서버에서 제공합니다. 별도 프론트엔드 빌드 환경은 추가하지 않습니다.
- **Django admin**: MVP의 신청 CRUD와 상태 관리 화면으로 사용할 예정입니다. 별도 관리자 신청 목록 화면은 MVP 이후 항목입니다.
- **django-environ**: 관리 명령·WSGI·ASGI가 같은 설정 로딩 경로를 사용하도록 Django 설정에서 `.env`를 읽고 boolean·목록을 해석합니다.
- **uv / Ruff / Django test runner**: 런타임 의존성과 개발 의존성을 분리하고, 별도 테스트 프레임워크 없이 필요한 계약을 검증합니다.

교육과 신청은 현재 하나의 앱에 둡니다. 단순 CRUD에는 Service·Repository·Selector 계층을 강제하지 않고, 실제 재사용·트랜잭션 책임이 생기면 필요한 부분만 분리합니다.

## 환경과 패키지 관리

uv는 `[tool.uv] package = false`인 비패키지 방식으로 사용합니다. 애플리케이션 자체를 빌드·설치할 필요가 없으므로 `[build-system]`을 두지 않습니다. 배포용 Python 라이브러리의 build backend 규칙과 구분합니다.

런타임 직접 의존성은 Django, DRF, `psycopg[binary]`, `django-environ`이고 개발 직접 의존성은 Ruff입니다. 추가 패키지는 해당 기능에 필요할 때 도입합니다. 환경 설치는 `uv sync --locked`, 실행은 `uv run`을 사용하며 `uv.lock`을 함께 관리합니다.

Django 기본 파일은 다음 명령으로 생성했습니다. 새 checkout에서 다시 실행하거나 기존 생성 파일을 덮어쓰는 명령이 아닙니다.

```powershell
New-Item -ItemType Directory src
uv run django-admin startproject config src
New-Item -ItemType Directory src/education
uv run django-admin startapp education src/education
```

생성 결과에서 앱 등록과 프로젝트 설정만 조정합니다. Django 기본 인증·admin·CSRF middleware를 유지합니다. `tests.py`는 `tests/` 패키지로 전환했으며 두 모듈을 함께 두지 않습니다.

설정은 `src/config/settings.py` 하나에서 환경 변수로 주입합니다. Django 설정은 django-environ으로 저장소 루트의 `.env`를 자동 로딩하며, 이미 주입된 환경 변수를 우선한다. `.env`가 없어도 필요한 환경 변수를 직접 주입하면 실행할 수 있습니다. uv의 `--env-file`은 중복 사용하지 않습니다. secret key, DB 이름·사용자·비밀번호가 없거나 비어 있으면 값 노출 없이 설정 오류로 중단합니다. DEBUG 기본값은 false이며 django-environ의 boolean 해석을 따릅니다(`true`/`1`/`yes`/`on`/`y`/`ok`는 true, 대소문자와 앞뒤 공백 무시). 허용 host는 목록으로 읽은 뒤 각 항목의 공백과 빈 항목을 제거합니다. 로컬 예제는 DEBUG=true와 loopback host를 사용합니다. 언어는 한국어, 시간대는 `Asia/Seoul`, timezone-aware datetime을 사용합니다.

Compose는 개발용 DB만 실행하고 포트를 loopback에만 공개합니다. 로컬 계정은 테스트 DB 생성 권한이 있으며 운영에 재사용하지 않습니다. named volume과 실제 `.env`를 보호하고 정지 시 volume을 삭제하지 않습니다.

## 검증과 변경 관리

README의 명령으로 Django check, migration 변경 누락 검사, `test education`, Ruff lint·format 검사를 수행합니다. 테스트는 PostgreSQL의 별도 테스트 DB를 사용합니다. 실제 `.env`와 격리한 파일 로딩·환경 변수 우선순위·설정 오류·파싱, 실제 DB 쿼리, 관리자 로그인 화면을 확인하고, 정적 파일은 실제 개발 서버에서 별도로 확인합니다. 실패를 코드 오류와 환경 문제로 구분하며 미검증 항목을 성공으로 기록하지 않습니다.

Ruff는 Python 3.14를 대상으로 프로젝트 소유 코드만 검사합니다. 에이전트 스킬·template managed 파일과 도구 캐시는 검사·자동 수정하지 않습니다. 주석과 docstring은 프로젝트의 한국어 정책을 따르되 Django가 생성한 기존 설명은 유지합니다.

GitHub Flow의 기준 브랜치는 `main`, 작업 브랜치는 `feature/<change-name>`입니다. 계획과 구현은 같은 브랜치에서 별도 커밋으로 관리하고 검증 후 PR로 검토·병합합니다. Conventional Commits의 영어 type과 한국어 제목을 사용합니다.

`AGENTS.md`는 로컬 실행 지침이며 현재 Git에서 제외되어 있습니다. 다른 checkout에 전달할 규약은 이 문서와 README에도 기록합니다. `openspec/config.yaml`에는 OpenSpec에 필요한 맥락과 artifact별 지침만 간결하게 유지합니다. 별도 constitution이나 custom schema는 만들지 않습니다.
