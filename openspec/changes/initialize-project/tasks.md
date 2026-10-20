# Tasks

이번 change는 개발 환경·도구·문서 초기 구성이다. `.openspec.yaml`의 `skip_specs: true`에 따라 delta spec은 생략하며 구현 기준은 [design.md](design.md)를 따른다. 교육·신청 기능과 우대 항목의 구현 작업은 포함하지 않는다.

## 1. 의존성과 개발 도구

- [ ] 1.1 `.python-version`에 `3.14`, `pyproject.toml`에 Python 지원 범위 `>=3.14,<3.15`와 `Django==6.1.2`, 호환되는 DRF 3.x·`psycopg[binary]` 3.x, 개발 그룹의 Ruff를 선언하고 `uv.lock`을 생성한다. `[tool.uv]`의 `package = false`를 명시하고 프로젝트 자체의 `[build-system]`은 추가하지 않는다. 공식 호환성 정보와 `uv sync --locked` 성공, `uv run python --version` 및 `uv run django-admin --version`의 결과가 각각 Python 3.14 계열과 Django 6.1.2인지 확인해 버전 조합과 재현 가능한 설치를 검증한다.
- [ ] 1.2 Ruff의 `target-version`을 `py314`로 설정하고 프로젝트 소유 코드의 검사 범위를 지정한다. `uv run ruff check .`와 `uv run ruff format --check .`가 도구 설치·template managed 파일을 대상으로 삼지 않는지 설정과 파일 목록으로 확인한다. 이후 생성할 `src/`도 같은 검사 범위에 포함한다.
- [ ] 1.3 README에 프로젝트 개요, 기술 스택과 의존성 설치 절차를 작성한다. `uv sync --locked`가 문서에 적힌 작업 디렉터리와 명령 그대로 실행되는지 확인하고, 아직 전체 MVP가 구현되지 않았음을 명시한다.

## 2. 로컬 PostgreSQL과 환경 변수

- [ ] 2.1 `.env.example`에 Django secret key·DEBUG·허용 host와 PostgreSQL 연결 변수의 로컬 개발용 예시 및 설명을 추가한다. `DJANGO_DEBUG=true`, `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`, `POSTGRES_HOST=127.0.0.1`을 로컬 예시로 명시한다. 기존 ignore 규칙에서 `.env`는 제외되고 `.env.example`은 추적 가능한지 `git check-ignore`로 확인하며 실제 비밀값이 포함되지 않았는지 검토한다.
- [ ] 2.2 `postgres:18.6-bookworm` 이미지의 `db` 서비스, loopback 포트 바인딩, healthcheck, `/var/lib/postgresql`에 마운트하는 named volume을 갖는 `compose.yaml`을 작성한다. Docker daemon을 확인한 뒤 `docker compose config --quiet`와 `docker compose up -d --wait db`로 구문과 DB readiness를 검증한다. `docker compose exec db postgres --version`으로 PostgreSQL 18.6을 확인하고, volume 대상과 기본 `PGDATA`가 각각 `/var/lib/postgresql`, `/var/lib/postgresql/18/docker`인지 확인한다. 설정 조회 시 비밀값이 담긴 전체 Compose 출력을 남기지 않는다.
- [ ] 2.3 README에 예제 복사 및 개발용 secret key·DB 비밀번호 준비를 포함한 `.env` 설정, 포트 충돌 시 설정, DB 기동·중지, 로컬 전용 계정과 테스트 DB 생성 권한을 문서화한다. DEBUG와 허용 host의 예시가 로컬 개발용임을 명시한다. 문서의 변수 이름이 Compose 및 예제 파일과 일치하고 volume을 삭제하는 종료 명령이 없는지 확인한다.

## 3. Django 프로젝트와 초기 검증

- [ ] 3.1 저장소 루트에서 `src/`를 준비하고 `uv run django-admin startproject config src`를 실행한 다음, `src/education/`을 준비하고 `uv run django-admin startapp education src/education`을 실행한다. 기본 골격 파일은 수작업으로 작성하지 않으며 생성된 `manage.py`, 설정·ASGI·WSGI 진입점, `AppConfig`, migration 패키지와 기본 admin URL의 존재를 확인한다. 설정 편집과 `check` 실행은 3.2에서 수행한다. 생성 명령의 기본 파일 외에 업무 모델·페이지·API와 빈 미래용 폴더는 추가하지 않는다.
- [ ] 3.2 `INSTALLED_APPS`에 `education`의 `AppConfig`와 `rest_framework`를 등록하고 환경 변수로 Django와 PostgreSQL을 설정한 뒤 한국어·`Asia/Seoul`·timezone-aware datetime을 적용한다. uv의 `--env-file .env` 경로를 사용하고 dotenv 패키지는 추가하지 않는다. DEBUG 문자열 해석·누락 시 false 기본값, 쉼표로 구분한 허용 host의 목록 변환, 필수 환경 변수 누락 시 비밀값 없는 설정 오류를 좁은 자동 테스트로 검증한다. 설정 적용 후 `uv run --env-file .env python src/manage.py check`로 앱 등록과 PostgreSQL을 사용하는 설정·URL 구성을 확인한다.
- [ ] 3.3 새 로컬 PostgreSQL에 `uv run --env-file .env python src/manage.py migrate --noinput`을 실행한다. `showmigrations`로 내장 migration 적용 상태를 확인하고 `makemigrations --check --dry-run`으로 업무 모델 migration이 생성되지 않았는지 확인한다. 공유·운영 DB는 사용하지 않는다.
- [ ] 3.4 Django가 생성한 `src/education/tests.py`를 기존 테스트를 보존하며 `src/education/tests/` 패키지로 전환하고 `__init__.py`와 테스트 모듈을 둔다. `tests.py`와 `tests/`가 공존하지 않는지 확인하고, 실제 PostgreSQL 연결의 vendor·간단한 쿼리 결과와 `/admin/login/`의 정상 응답을 확인하는 smoke test를 추가한다. `uv run --env-file .env python src/manage.py test education`으로 설정 테스트와 함께 발견·실행되어 통과하는지 확인한다. 외부 서비스나 업무 DB 동작을 mock으로 대체하지 않는다.
- [ ] 3.5 README에 Django check·migration·테스트·관리자 계정 생성·개발 서버 실행 명령을 추가한다. 문서의 `runserver` 명령과 로컬 DEBUG·허용 host 설정으로 서버를 기동하고 `/admin/login/` 및 화면에서 참조하는 admin CSS 요청이 HTTP 200으로 응답하며 스타일이 적용되는지 확인한다. 검사·테스트 결과와 함께 Ruff lint·format 검사를 통과시킨다.

## 4. 프로젝트 거버넌스와 후속 작업 기록

- [ ] 4.1 `docs/architecture.md`에 실제 생성한 폴더 구조, 최소 의존성, 화면 기술, 설정·DB·테스트 방식과 선택 이유를 기록하고 README에서 연결한다. 문서의 파일 경로와 설치 패키지가 실제 구성 및 lockfile과 일치하는지 확인한다.
- [ ] 4.2 README에 초기 구성 완료 상태, 후속 MVP 기능, MVP 이후 우대 항목 네 가지를 구분해 기록한다. 자동 안내 메일은 별도의 미결정 선택 기능으로 남기며 과제 원문에 있는 항목이 누락되거나 구현 완료로 오인되지 않는지 대조한다.
- [ ] 4.3 `AGENTS.md`의 Project Rules에 프로젝트 구조·규약 문서 참조와 검증 명령을 반영한다. 이 애플리케이션은 uv 비패키지 방식이며 배포 패키지용 build backend 규칙의 대상이 아님을 명시한다. managed block·GitNexus 구역·template 관리 파일은 유지하고, 기존 `.git/info/exclude` 및 추적 상태를 변경하지 않았는지 확인한다. 공유해야 할 규약이 이 로컬 파일에만 남지 않도록 `docs/architecture.md`와 대조한다.
- [ ] 4.4 `openspec/config.yaml`에 프로젝트 맥락, MVP 경계, 규약 문서 참조와 proposal·design·tasks별 지침 및 apply 검증 지침을 반영한다. 기본 schema와 기존 언어 정책을 보존하고, `openspec context --json` 및 `openspec instructions tasks --change initialize-project --json`으로 root 해석과 artifact별 지침 전달을 확인한다.

## 5. 통합 완료 확인

- [ ] 5.1 의존성 설치·DB readiness·Django check·migration·테스트·Ruff의 최종 결과를 모아 README 절차와 일치하는지 확인한다. 이미 성공했고 이후 변경의 영향을 받지 않은 검사는 반복하지 않는다. 환경 문제로 수행하지 못한 검증이 있으면 항목과 원인을 남기고 완료로 표시하지 않는다.
- [ ] 5.2 `openspec validate initialize-project --strict`로 계획의 정합성을 확인하고, 최종 변경 목록에서 교육·신청 기능·우대 기능·외부 배포·managed 파일 변경이 추가되지 않았는지 확인한다. 명세 생략 상태와 초기 구성 범위, 문서 링크를 함께 검토한다.
