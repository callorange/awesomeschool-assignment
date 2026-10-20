# 어썸스쿨 교육 신청 시스템

교육 소개 → 신청 접수 → 신청 관리를 구현하는 Django 개발 과제입니다.
현재 초기 개발 환경과 Django 기본 관리자 로그인 화면을 제공합니다. 교육·신청 업무 기능은 아직 구현하지 않았습니다.

## 기술 스택

| 구분 | 선택 |
| --- | --- |
| 언어 | Python 3.14 |
| 웹 / API | Django 6.1.2 / Django REST Framework |
| 데이터베이스 | PostgreSQL 18.6 / Psycopg 3 |
| 화면 | Django Templates, CSS, JavaScript `fetch` |
| 환경 / 검사 | uv, django-environ, Ruff, Django test runner |

uv 비패키지 방식으로 의존성과 실행 환경을 관리합니다. 프로젝트 자체의 배포 패키지는 만들지 않으며, `uv.lock`은 Git으로 관리합니다.

## 실행 준비

저장소 루트에서 실행합니다. uv와 Docker Compose v2를 설치하고 Docker Desktop의 Linux 컨테이너 엔진을 실행해야 합니다. uv는 `.python-version`에 맞는 Python을 선택하며, 필요한 경우 Python을 내려받습니다.

```text
uv sync --locked
```

### 로컬 환경 변수

`.env.example`을 `.env`로 복사합니다.

```powershell
Copy-Item .env.example .env
```

Linux/macOS에서는 `cp .env.example .env`를 사용합니다. 아래 명령은 빈 개발용 secret key와 DB 비밀번호에 임의 값을 기록하며 값을 출력하지 않습니다. 새로 복사한 `.env`에서 한 번 실행합니다.

```text
uv run python -c "from pathlib import Path; import secrets; p = Path('.env'); s = p.read_text(encoding='utf-8'); s = s.replace('DJANGO_SECRET_KEY=\n', 'DJANGO_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n'); s = s.replace('POSTGRES_PASSWORD=\n', 'POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n'); p.write_text(s, encoding='utf-8')"
```

로컬 예시는 `DJANGO_DEBUG=true`, `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`, `POSTGRES_HOST=127.0.0.1`입니다. 실제 `.env`는 Git에서 제외되며 운영 환경에 재사용하지 않습니다.

Django 설정은 django-environ으로 저장소 루트의 `.env`를 자동으로 읽습니다. 이미 주입된 환경 변수가 파일보다 우선하며, `.env` 없이 필요한 환경 변수를 직접 주입해도 실행할 수 있습니다. uv의 `--env-file` 옵션은 필요하지 않습니다. secret key와 DB 이름·사용자·비밀번호는 누락되거나 비어 있으면 설정 오류로 중단합니다. DEBUG 기본값은 false이며 django-environ의 boolean 해석을 따릅니다(`true`/`1`/`yes`/`on`/`y`/`ok`는 true, 대소문자와 앞뒤 공백 무시).

### 데이터베이스

```text
docker compose config --quiet
docker compose up -d --wait db
docker compose exec db postgres --version
```

호스트에서 Django를 실행하고 Compose로 DB만 실행합니다. 5432 포트가 이미 사용 중이면 `.env`의 `POSTGRES_PORT`를 빈 포트로 변경합니다. Django와 Compose가 같은 값을 사용합니다.

DB는 loopback에만 공개되며 named volume을 `/var/lib/postgresql`에 마운트합니다. PostgreSQL 18 이미지의 기본 `PGDATA`는 `/var/lib/postgresql/18/docker`입니다. 로컬 Compose 계정은 테스트 DB를 생성할 권한이 있으며 공유·운영 DB 계정으로 사용하지 않습니다.

중지할 때는 데이터를 보존합니다.

```text
docker compose down
```

volume을 삭제하지 마세요. 기존 volume이 있으면 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` 변경만으로 기존 계정이나 DB가 바뀌지 않습니다.

### Django 실행

```text
uv run python src/manage.py check
uv run python src/manage.py migrate --noinput
uv run python src/manage.py createsuperuser
uv run python src/manage.py runserver 127.0.0.1:8000 --noreload
```

브라우저에서 [관리자 화면](http://127.0.0.1:8000/admin/)에 접근합니다. 관리자 계정은 `createsuperuser`의 대화형 입력으로 만들며 미리 제공되는 계정·비밀번호는 없습니다. 현재 교육·신청 모델은 없으므로 해당 관리 메뉴도 아직 없습니다. 사이트 루트의 소개 화면은 후속 MVP에서 구현합니다.

로컬 DEBUG 설정과 Django 기본 `staticfiles`로 관리자 CSS를 제공합니다. 실행 후 로그인 폼에 스타일이 적용되고 브라우저 개발자 도구에서 `/static/admin/css/base.css`가 HTTP 200으로 응답하는지 확인합니다. 이 구성은 운영용 정적 파일 배포가 아닙니다.

## 검증

DB가 실행 중이고 `.env`가 준비된 상태에서 저장소 루트에서 실행합니다.

```text
uv run python src/manage.py check
uv run python src/manage.py makemigrations --check --dry-run
uv run python src/manage.py test education
uv run ruff check .
uv run ruff format --check .
```

테스트는 실제 PostgreSQL의 별도 `test_awesomeschool` DB를 생성·삭제합니다. `POSTGRES_DB`를 바꾸면 테스트 DB 이름도 이에 맞춰 바뀝니다. 공유·운영 DB에 연결한 상태로 실행하지 않습니다. 격리된 `.env` 로딩·환경 변수 우선순위·필수값 누락 및 빈 값·boolean과 host 목록 해석, PostgreSQL 연결과 관리자 로그인 화면을 검증합니다. 외부 메일·Google·AWS 연결은 사용하지 않습니다.

Ruff 검사 대상은 `src/`의 Python 파일과 `pyproject.toml`입니다. 설치된 에이전트 스킬·템플릿 관리 파일은 검사하거나 자동 수정하지 않습니다.

## 구현 범위

초기 구성 이후 다음 MVP를 순서대로 구현합니다.

- 교육명·한 줄 소개·커리큘럼·대표 이미지가 있는 소개 화면
- 이름·이메일·주소·연락 가능 날짜를 입력받는 반응형 신청 폼과 비동기 제출
- Django admin의 신청 조회·수정·삭제와 접수 / 확인중 / 완료 상태 관리
- DRF 신청 GET/POST API: 익명 신청 생성과 관리자 전용 개인정보 조회

MVP 이후에도 다음 예정 사항을 유지합니다.

- 별도 관리자 신청 목록 화면
- Google Spreadsheet API를 통한 목록 내보내기
- AWS 사용 계획 또는 배포 구성

자동 안내 메일은 별도의 선택 기능이며 MVP 포함 여부는 아직 결정하지 않았습니다.

## 개발 흐름

GitHub Flow를 따릅니다. `main`에서 `feature/<change-name>` 브랜치를 만들고, 같은 브랜치에서 계획과 구현을 별도 커밋으로 기록합니다. 관련 검증 후 PR을 검토·병합하고 작업 브랜치를 정리합니다. 커밋은 Conventional Commits의 영어 type과 한국어 제목을 사용합니다.

폴더 구조와 기술 선택 이유는 [아키텍처와 개발 규약](docs/architecture.md)을 참고하세요. 과제 원문은 [교육 신청 시스템 구현 과제](docs/awesomeschool-assignment.md), 현재 계획은 [initialize-project](openspec/changes/initialize-project/proposal.md)에 있습니다.

## AI 코딩 보조 도구 활용

개발 과정에서 사용한 AI 코딩 보조 도구와 활용 이유는 다음과 같습니다. 기능 구현이 진행되면 사용 내역을 함께 갱신합니다.

| 도구 | 사용 내역과 활용 이유 |
| --- | --- |
| Codex | 코딩 에이전트로 사용하여 프로젝트 구성, 코드 작성·수정, 테스트 실행과 문서 작성을 보조합니다. |
| [django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) | 에이전트에 Django 코딩 skill을 추가하여 Django 구현과 검토에 필요한 지침을 제공합니다. |
| [GitNexus](https://github.com/abhigyanpatwari/GitNexus) | 에이전트의 로컬 프로젝트 검색을 최적화하고 코드 구조와 의존 관계를 파악하는 데 사용합니다. |
| [ponytail](https://github.com/dietrichgebert/ponytail) | 에이전트의 과도한 추상화를 방지하고 현재 요구사항에 필요한 범위로 구현을 유지하는 데 사용합니다. |
| [OpenSpec](https://openspec.dev/) | 명세 기반 개발(SDD)을 진행하기 위해 변경 제안, 설계와 작업 목록을 정리하고 구현 진행 상태를 관리합니다. |
