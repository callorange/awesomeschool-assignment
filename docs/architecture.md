# 아키텍처와 기술 선택

교육 소개 → 신청 접수 → 신청 관리라는 하나의 흐름을 단일 Django 프로젝트에서 구현합니다. 교육 소개는 Django Templates와 Tailwind CSS로 제공하며 신청 기능은 후속 change에서 추가합니다. 실행 명령과 구현 예정 목록은 [README](../README.md), 원래 요구사항은 [과제 문서](awesomeschool-assignment.md)를 기준으로 합니다.

## 프로젝트 구조

| 경로 | 책임 |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.python-version` | Python·의존성·개발 도구와 실행 환경 |
| `compose.yaml`, `.env.example` | 로컬 PostgreSQL과 환경 변수 계약 |
| `src/manage.py` | Django 관리 명령 진입점 |
| `src/config/` | 설정·URL·ASGI·WSGI 진입점 |
| `src/education/` | 교육 소개 모델·초기화 명령과 향후 신청 기능을 담을 앱 |
| `src/education/migrations/` | 교육 모델의 DB schema 변경 이력 |
| `src/templates/` | 공통 layout과 기능별 template를 담는 통합 폴더 |
| `src/static/` | 빌드 CSS 등 프로젝트 정적 자산을 담는 통합 폴더 |
| `frontend/styles.css`, `package.json`, `package-lock.json` | Tailwind 입력·npm CLI 명령·설치 조합 |
| `presets/education/` | 초기화용 JSON 프리셋과 이미지 원본 |
| `src/education/tests/` | 설정·모델·프리셋·교육 페이지·관리자 화면 테스트 |
| `media/` | dev에서 생성되는 실행 중 미디어 파일; Git 제외 |
| `docs/` | 과제 원문과 프로젝트 설계 설명 |
| `openspec/` | 프로젝트 맥락과 change별 계획·진행 상태 |

프로젝트 소유 template와 static은 앱별로 만들지 않고 `src/templates/`와 `src/static/`에 통합합니다. 공통 layout은 `src/templates/base.html`, 교육 화면은 `src/templates/education/`, 빌드 CSS는 `src/static/css/site.css`에 둡니다. Django의 TEMPLATES DIRS와 STATICFILES_DIRS에 통합 경로를 등록하며, Django admin 등 설치 앱의 자산 탐색은 유지합니다. Tailwind 탐색은 해당 template 경로로 제한하며 규칙·스킬 파일을 탐색하지 않습니다. 이미지 원본은 `presets/education/images/`에 포함하고 실행 시 선택한 media 저장소에 설정합니다.

## 기술 선택

- **Python 3.14 / Django 6.1.2**: 기존 호환성 제약이 없는 신규 프로젝트의 기준입니다. Django를 `6.1.2`로 고정하고 lockfile로 정확한 설치 조합을 재현합니다. 장기 운영 시 Django 6.1 지원 종료 전에 업그레이드하며 보안 패치를 계속 확인합니다.
- **DRF**: 과제에서 지정한 API 프레임워크입니다. 설치·앱 등록은 끝났으며 신청 API는 후속 구현입니다.
- **PostgreSQL 18.6 / Psycopg 3**: 개발·테스트 DB를 통일합니다. SQLite 대체 경로는 두지 않습니다. `postgres:18.6-bookworm`을 사용하고 volume은 `/var/lib/postgresql`에 마운트합니다.
- **Django Templates / Tailwind CSS / `fetch`**: 랜딩·교육 상세와 향후 신청 화면을 단일 서버에서 제공합니다. Tailwind CSS 4의 npm CLI를 개발 의존성으로 사용하며 별도 프론트 서버나 SPA는 만들지 않습니다. `frontend/styles.css`와 template를 입력으로 static CSS를 빌드하고 결과물을 저장소에 포함합니다. 평가자 실행에는 Node.js가 필요하지 않습니다.
- **Django admin**: MVP의 신청 CRUD와 상태 관리 화면으로 사용할 예정입니다. 별도 관리자 신청 목록 화면은 MVP 이후 항목입니다.
- **django-environ**: 관리 명령·WSGI·ASGI가 같은 설정 로딩 경로를 사용하도록 Django 설정에서 `.env`를 읽고 boolean·목록을 해석합니다.
- **uv / Ruff / Django test runner**: 런타임 의존성과 개발 의존성을 분리하고, 별도 테스트 프레임워크 없이 필요한 계약을 검증합니다.

현재 교육 소개는 education 앱에서 제공하며, 후속 신청 기능도 같은 앱에 구현할 계획입니다. 단순 CRUD에는 Service·Repository·Selector 계층을 강제하지 않고, 실제 재사용·트랜잭션 책임이 생기면 필요한 부분만 분리합니다.

## 환경과 패키지 관리

uv는 `[tool.uv] package = false`인 비패키지 방식으로 사용합니다. 애플리케이션 자체를 빌드·설치할 필요가 없으므로 `[build-system]`을 두지 않습니다. 배포용 Python 라이브러리의 build backend 규칙과 구분합니다.

공통 실행 의존성은 Django, DRF, `psycopg[binary]`, `django-environ`입니다. `prod` 그룹에는 `django-storages[s3]`, 기본 `dev` 그룹에는 `prod` 포함과 Ruff를 둡니다. local 그룹이나 별도 AWS extra는 만들지 않습니다. 로컬은 `uv sync --locked`, 운영은 `uv sync --locked --no-default-groups --group prod`로 설치합니다. 운영 설치 뒤 직접 가상환경 실행 또는 `uv run --no-sync`를 사용하여 dev가 다시 설치되지 않게 합니다. 추가 패키지는 해당 기능에 필요할 때 도입합니다. 환경 설치는 `uv sync --locked`, 실행은 `uv run`을 사용하며 `uv.lock`을 함께 관리합니다.

새 Django 프로젝트와 앱의 기본 골격은 LLM이 직접 작성하지 않고 Django의 `startproject`·`startapp` 명령으로 생성한 뒤 필요한 설정을 편집합니다. 기존 Django 기본 파일은 다음 명령으로 생성했습니다. 새 checkout에서 다시 실행하거나 기존 생성 파일을 덮어쓰는 명령이 아닙니다.

```powershell
New-Item -ItemType Directory src
uv run django-admin startproject config src
New-Item -ItemType Directory src/education
uv run django-admin startapp education src/education
```

생성 결과에서 앱 등록과 프로젝트 설정만 조정합니다. Django 기본 인증·admin·CSRF middleware를 유지합니다. `tests.py`는 `tests/` 패키지로 전환했으며 두 모듈을 함께 두지 않습니다.

설정은 `src/config/settings/base.py`(공통), `dev.py`(로컬 미디어), `prod.py`(S3·CloudFront)로 분리합니다. manage.py·ASGI·WSGI의 기본은 `config.settings.dev`이며 프로세스에 지정한 `DJANGO_SETTINGS_MODULE`을 보존합니다. 운영은 `config.settings.prod`를 프로세스 환경이나 관리 명령의 `--settings`로 명시합니다. `.env`를 읽기 전에 모듈이 선택되므로 `.env`에 설정 모듈을 적어 자동 전환하지 않습니다. Django 설정은 django-environ으로 저장소 루트의 `.env`를 자동 로딩하며, 이미 주입된 환경 변수를 우선한다. `.env`가 없어도 필요한 환경 변수를 직접 주입하면 실행할 수 있습니다. uv의 `--env-file`은 중복 사용하지 않습니다. secret key, DB 이름·사용자·비밀번호가 없거나 비어 있으면 값 노출 없이 설정 오류로 중단합니다. DEBUG 기본값은 false이며 django-environ의 boolean 해석을 따릅니다(`true`/`1`/`yes`/`on`/`y`/`ok`는 true, 대소문자와 앞뒤 공백 무시). 허용 host는 목록으로 읽은 뒤 각 항목의 공백과 빈 항목을 제거합니다. 로컬 예제는 DEBUG=true와 loopback host를 사용합니다. 언어는 한국어, 시간대는 `Asia/Seoul`, timezone-aware datetime을 사용합니다.

미디어 이미지는 FileField의 저장소 상대 이름으로 참조하고 template는 `.url`을 사용합니다. dev는 저장소 루트 `media/`와 `/media/`를 사용하고 DEBUG일 때만 Django가 제공합니다. dev에서는 AWS 백엔드를 로딩하거나 자격 증명을 조회하지 않습니다. prod는 비공개 S3에 `media/` prefix로 저장하고 CloudFront HTTPS URL로 공개 교육 이미지를 제공합니다. CloudFront OAC·버킷·IAM은 배포 환경에서 사전에 준비합니다. 운영은 DEBUG 활성화와 필수 host·버킷·리전·CloudFront 도메인 누락을 거부하며 로컬로 fallback하지 않습니다. IAM role과 SDK 기본 credential chain을 사용합니다. static CSS와 media의 책임은 분리하며 운영 static 배포는 별도 범위입니다.

Compose는 개발용 DB만 실행하고 포트를 loopback에만 공개합니다. 로컬 계정은 테스트 DB 생성 권한이 있으며 운영에 재사용하지 않습니다. named volume과 실제 `.env`를 보호하고 정지 시 volume을 삭제하지 않습니다.

개발·검증·Git 정책은 [개발 규약](development.md)을 따릅니다. 전체 문서의 역할은 [문서 안내](README.md)를 참고하세요.

## 교육 데이터와 프리셋

Education은 교육명·소개·미디어 FileField·목표·대상·시수별 커리큘럼·출처·수집일을 보관합니다. 목표·대상과 커리큘럼은 JSONField를 사용하며 입력 명령에서 구조와 교시 순서를 검증합니다. 프리셋 JSON과 이미지 원본은 앱의 실행 코드와 분리해 저장소 루트 `presets/education/`에 보관합니다. 초기화 명령은 `src/education/management/commands/`에 유지하고 Django `BASE_DIR`의 상위인 저장소 루트를 기준으로 프리셋을 찾습니다. 초기화를 실행할 배포물에도 이 폴더를 포함해야 합니다. 프리셋 원본은 Git으로 관리하며 직접 제공하는 static이나 실행 중 업로드 저장소로 사용하지 않습니다. `seed_educations`는 사전 검증 후 누락 교육만 추가하고 기존 교육과 이미지를 보존합니다. 이미지 키는 slug와 내용 해시로 만들고 저장소가 반환한 이름을 DB에 기록합니다. DB 오류 시 transaction은 롤백되지만 파일은 남을 수 있으므로 자동 삭제하지 않고 재실행에서 재사용합니다.
