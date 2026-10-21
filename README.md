# 어썸스쿨 교육 신청 시스템

교육 소개 → 신청 접수 → 신청 관리를 구현하는 Django 개발 과제입니다.
반응형 랜딩과 교육 상세, 히어로스쿨 교육 3개의 초기 데이터 설정을 제공합니다. 개발·운영 설정과 미디어 저장소를 구분하며 신청 기능은 아직 구현하지 않았습니다.

## 기술 스택

| 구분 | 선택 |
| --- | --- |
| 언어 | Python 3.14 |
| 웹 / API | Django 6.1.2 / Django REST Framework |
| 데이터베이스 | PostgreSQL 18.6 / Psycopg 3 |
| 화면 | Django Templates, Tailwind CSS (신청 비동기 제출에는 `fetch` 사용 예정) |
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

### 설정 선택과 운영 의존성

기본 `uv sync --locked`는 dev 그룹과 그 안에 포함된 prod 그룹을 설치합니다. 로컬 실행은 `config.settings.dev`를 사용하며 AWS 패키지가 설치되어 있어도 로컬 미디어만 사용합니다. 기본 실행 중 AWS 자격 증명 조회나 외부 연결은 없습니다.

운영에서는 다음과 같이 개발 도구를 제외합니다.

```text
uv sync --locked --no-default-groups --group prod
```

운영 프로세스를 시작하기 **전에** `DJANGO_SETTINGS_MODULE=config.settings.prod`를 지정합니다. 이 값은 프로젝트 `.env`가 아닌 실행 환경에서 지정합니다. 관리 명령은 `--settings=config.settings.prod`로도 선택할 수 있습니다. 운영 설치 후 명령 실행은 직접 가상환경 Python을 사용하거나 다음처럼 동기화를 생략합니다.

```text
uv run --no-sync python src/manage.py check --settings=config.settings.prod
```

운영은 `DJANGO_DEBUG=false`, 명시적인 `DJANGO_ALLOWED_HOSTS`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_S3_CUSTOM_DOMAIN`이 필요합니다. CloudFront 도메인은 scheme·경로·끝 슬래시 없는 host입니다. 버킷은 비공개로 유지하고 CloudFront OAC를 통한 원본 접근과 공개 viewer 접근을 준비합니다. 앱은 IAM role 등 SDK 기본 credential chain을 사용합니다. 키를 저장소에 기록하지 않습니다. 버킷·CloudFront·IAM 리소스 생성과 실제 배포, 운영 static CSS 서빙은 이 프로젝트의 이번 구현 범위가 아닙니다.

개발 미디어는 `media/`에 저장되며 DEBUG일 때 `/media/`에서 제공합니다. 운영 이미지는 S3에 저장하고 CloudFront로 제공합니다. 설정을 바꿔도 기존 로컬 파일이 S3로 복사되지는 않습니다.

### 데이터베이스

```text
docker compose config --quiet
docker compose up -d --wait db
docker compose exec db postgres --version
```

호스트에서 Django를 실행하고 Compose로 DB만 실행합니다. 기본 포트 매핑은 `127.0.0.1:15432:5432`입니다. 호스트의 15432 포트가 이미 사용 중이면 `.env`의 `POSTGRES_PORT`를 빈 포트로 변경합니다. Django와 Compose가 같은 값을 사용합니다.

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
uv run python src/manage.py seed_educations
uv run python src/manage.py createsuperuser
uv run python src/manage.py runserver 127.0.0.1:8000 --noreload
```

초기 데이터 명령은 `presets/education/education_presets.json`과 같은 폴더의 `images/`를 읽어 프롬프트·감정탐험·관계 히어로 교육과 이미지를 설정합니다. 초기 설정을 실행할 환경에는 `presets/education/`도 포함해야 합니다. 신규 교육에는 코치 출강 방식·상담 후 일정과 조건을 협의한다는 진행 안내·상담 접수 활성 상태를 설정하며, 과제용 운영 정책은 편집 설명으로 구별합니다. 반복 실행하면 기존 교육의 운영 정보와 이미지 참조를 보존하고 없는 교육만 추가합니다. 입력 오류는 모델과 공통인 검증으로 쓰기 전에 거부하며 저장 실패 시 DB 변경은 롤백됩니다. 저장소 파일은 남을 수 있고 다음 실행에서 재사용합니다. dev 모드에서는 원본 사이트에 접속하거나 AWS 자격 증명을 요구하지 않습니다.

운영 seed는 준비된 S3에 이미지를 업로드하는 명시적 작업입니다. `uv run --no-sync python src/manage.py seed_educations --settings=config.settings.prod`를 사용하며 설정 전환 자체로 기존 파일이 복사되지는 않습니다. 실제 AWS 업로드·리소스 생성은 기본 개발·테스트에서 수행하지 않습니다.

신규 이미지는 `education/<media_id의 32자 hex>/images/`에 저장합니다. `media_id`는 DB 저장 전에 생성하는 교육별 UUIDv7이며 slug와 관계없이 유지하고 편집 입력에서 제외합니다. 프리셋에는 고정 UUIDv7을 기록합니다. 초기화 명령은 원본 내용의 SHA256을 파일명으로 사용해 실패 후 남은 파일을 재사용하고, 일반 파일 저장은 원본 이름 대신 UUID를 사용합니다. 기존 이미지 경로는 유지하며 초기화 재실행이나 slug 변경으로 파일을 일괄 이동하지 않습니다.

교육 삭제·일반 모델 저장을 통한 이미지 교체가 commit되면 다른 교육이 참조하지 않는 이전 파일만 정리합니다. rollback과 공유 파일은 보존하며 저장소 삭제 실패는 키·예외 종류로 기록합니다. 운영 모드에서는 S3 파일 삭제를 수반합니다. `QuerySet.update()`·`bulk_update()`·직접 SQL은 이 정리를 우회하므로 이미지 편집에는 일반 모델 저장을 사용해야 합니다. 새 파일 저장 후 DB rollback·프로세스 중단으로 고아 파일이 남을 수 있으며 자동 재시도·전수 청소는 제공하지 않습니다. 초기화 실패 파일의 재사용과 프리셋 원본 보존은 유지합니다.

초기 콘텐츠는 [프롬프트 히어로](https://hero-school.net/visit/prompt/), [감정탐험 히어로](https://hero-school.net/visit/emotion/), [관계 히어로](https://hero-school.net/visit/relationship/)의 공개 정보를 사용합니다. 프로그램명·교시 주제·활동명은 원문 기준이고 소개·목표·대상·설명은 과제용으로 요약·편집했습니다. 원문·원본 이미지 URL, 수집일, 편집 설명은 `presets/education/education_presets.json`에만 기록하며 DB에 저장하거나 상세 화면에 표시하지 않습니다. 이미지와 원문 권리는 각 권리자에게 있습니다.

브라우저에서 [관리자 화면](http://127.0.0.1:8000/admin/)에 접근합니다. 관리자 계정은 `createsuperuser`의 대화형 입력으로 만들며 미리 제공되는 계정·비밀번호는 없습니다. 관리자 화면은 기존 기본 기능을 유지하며 교육 편집 전용 메뉴와 신청 기능은 이번 범위에 포함하지 않습니다. [랜딩](http://127.0.0.1:8000/)에서 교육 3개를 탐색하고 각 상세에서 목표·추천대상·시수별 커리큘럼을 확인할 수 있습니다.

로컬 DEBUG 설정과 Django 기본 `staticfiles`로 관리자 CSS를 제공합니다. 실행 후 로그인 폼에 스타일이 적용되고 브라우저 개발자 도구에서 `/static/admin/css/base.css`가 HTTP 200으로 응답하는지 확인합니다. 이 구성은 운영용 정적 파일 배포가 아닙니다.

프로젝트 template는 `src/templates/`, static은 `src/static/`에서 통합 관리합니다. `presets/education/`은 초기 데이터 원본이며, 실행 중 교육 이미지는 dev의 `media/` 또는 prod의 S3에 저장합니다. 원본과 저장소 파일의 관리 원칙은 [아키텍처](docs/architecture.md)를 따릅니다.

현재 education migration은 `0001_initial`과 Django가 재생성한 `0002_improve_education_model`입니다. 개발 이력을 정리하면서 로컬 DB를 초기화했으며, 이전 0002~0006 적용 DB에 그대로 덮어 적용하는 용도가 아닙니다. DB 초기화는 기존 교육·신청·관리자 계정 등 모든 DB 데이터를 삭제하므로 일반 실행 준비에는 필요하지 않습니다.

### CSS 개발 도구

평가자는 저장소에 포함된 CSS로 실행할 수 있으므로 Node.js 설치나 빌드가 필요하지 않습니다. 화면을 수정하는 개발자는 Node.js와 npm을 준비하고 다음 명령을 실행합니다.

```text
npm ci
npm run build:css
```

변경 감시는 `npm run watch:css`를 사용합니다. Tailwind는 npm CLI와 `package-lock.json`으로 설치 조합을 재현합니다. template나 `frontend/styles.css`를 바꾸면 CSS를 재빌드하고 생성물도 함께 반영합니다. 자세한 정책은 [개발 규약](docs/development.md)을 따릅니다.

CSS가 표시되지 않으면 `DJANGO_DEBUG=true`와 실행 중인 서버의 설정 모듈을 확인하고, `uv run python src/manage.py findstatic css/site.css --verbosity 2`로 파일 탐색을 검사합니다. `/static/css/site.css`가 HTTP 200인지 확인합니다. 위 `--noreload` 명령으로 실행했다면 Python 코드·설정 변경 후 서버를 다시 시작해야 합니다.

## 검증

DB가 실행 중이고 `.env`가 준비된 상태에서 저장소 루트에서 실행합니다.

```text
uv run python src/manage.py check
uv run python src/manage.py makemigrations --check --dry-run
uv run python src/manage.py test education
uv run ruff check .
uv run ruff format --check .
```

테스트는 실제 PostgreSQL의 별도 `test_awesomeschool` DB를 생성·삭제합니다. `POSTGRES_DB`를 바꾸면 테스트 DB 이름도 이에 맞춰 바뀝니다. 공유·운영 DB에 연결한 상태로 실행하지 않습니다. 격리된 settings 패키지의 .env 로딩·우선순위·필수값·모드 선택, PostgreSQL 모델과 slug 고유성, 프리셋 보존·실패 시 롤백·파일 재사용, 랜딩·상세 렌더링·escaping·404와 관리자 화면을 검증합니다. 미디어는 임시 디렉터리에 격리하고 CloudFront URL은 외부 호출 없이 검사합니다. 외부 메일·Google·AWS 연결은 사용하지 않습니다.

Ruff 검사 대상은 `src/`의 Python 파일과 `pyproject.toml`입니다. 설치된 에이전트 스킬·템플릿 관리 파일은 검사하거나 자동 수정하지 않습니다.

## 구현 범위

구현 완료:

- 반응형 랜딩과 교육 3개의 상세 소개: 교육명·한 줄 소개·대표 이미지·목표·추천대상·시수별 커리큘럼·운영 방식·진행 안내·상담 접수 상태
- 누락 교육만 추가하는 초기 데이터 명령과 로컬 미디어·S3/CloudFront 저장소 설정
- dev/prod 의존성 그룹, base/dev/prod settings 분리, Tailwind CLI 빌드

교육 신청은 담당자와 상담한 뒤 일정과 진행 조건을 협의하는 접수 단계로 해석합니다. 과제의 연락 가능 날짜는 상담 가능한 날짜이며 교육 희망일과는 구별합니다. `operation_type`은 코치 출강·코스웨어를 구분하고 `operation_note`는 일반 텍스트 안내, `is_accepting_inquiries`는 접수 허용 여부입니다. 접수 중단 교육도 소개는 공개합니다. 이번에는 읽기 전용 안내와 데이터 계약만 제공하며 신청·교육 편집 기능은 아직 없습니다. 후속 신청 API는 이 접수 허용 값을 서버에서 검사해야 합니다. 기수·반·좌석 예약·결제는 범위에 포함하지 않습니다.

후속 MVP:

- 이름·이메일·주소·연락 가능 날짜를 입력받는 반응형 신청 폼과 비동기 제출
- Django admin의 신청 조회·수정·삭제와 접수 / 확인중 / 완료 상태 관리
- DRF 신청 GET/POST API: 익명 신청 생성과 관리자 전용 개인정보 조회

MVP 이후에도 다음 예정 사항을 유지합니다.

- 별도 관리자 신청 목록 화면
- Google Spreadsheet API를 통한 목록 내보내기
- AWS 사용 계획 또는 배포 구성

자동 안내 메일은 별도의 선택 기능이며 MVP 포함 여부는 아직 결정하지 않았습니다.

## 개발 흐름

브랜치·커밋·병합 정책은 [개발 규약](docs/development.md)을 따릅니다. 주제별 거버넌스는 [문서 안내](docs/README.md), 폴더 구조와 기술 선택 이유는 [아키텍처](docs/architecture.md)를 참고하세요. 과제 원문은 [교육 신청 시스템 구현 과제](docs/awesomeschool-assignment.md), 초기 구성의 완료 기록은 [initialize-project](openspec/changes/archive/2026-10-20-initialize-project/proposal.md), 교육 화면의 설계·검증 기록은 [add-front-end](openspec/changes/archive/2026-10-21-add-front-end/tasks.md)에 있습니다. `add-front-end`는 구현과 메인 명세 동기화를 완료하고 2026-10-21에 archive했습니다.

## AI 코딩 보조 도구 활용

개발 과정에서 사용한 AI 코딩 보조 도구와 활용 이유는 다음과 같습니다. 기능 구현이 진행되면 사용 내역을 함께 갱신합니다.

| 도구 | 사용 내역과 활용 이유 |
| --- | --- |
| Codex | 환경별 Django 설정과 저장소·프리셋 명령·교육 화면을 구현하고 서버 테스트·반응형 브라우저 검증·문서 동기화를 보조했습니다. |
| [django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) | 에이전트에 Django 코딩 skill을 추가하여 Django 구현과 검토에 필요한 지침을 제공합니다. |
| [GitNexus](https://github.com/abhigyanpatwari/GitNexus) | 에이전트의 로컬 프로젝트 검색을 최적화하고 코드 구조와 의존 관계를 파악하는 데 사용합니다. |
| [ponytail](https://github.com/dietrichgebert/ponytail) | 에이전트의 과도한 추상화를 방지하고 현재 요구사항에 필요한 범위로 구현을 유지하는 데 사용합니다. |
| [OpenSpec](https://openspec.dev/) | 명세 기반 개발(SDD)을 진행하기 위해 변경 제안, 설계와 작업 목록을 정리하고 구현 진행 상태를 관리합니다. |
