# 어썸스쿨 교육 신청 시스템

교육 소개를 확인한 방문자가 상담을 신청하고, 연락 가능 날짜에 안내를 받는 Django 사전 과제입니다.
신청은 수강 확정이 아닌 **상담 접수**로 해석했습니다. 연락 가능 날짜도 교육 희망일과 구분합니다.

[실행 방법](#로컬-실행) · [기능 확인](#실행-후-확인) · [설계 의도](#주요-설계-의도) · [과제 원문](docs/awesomeschool-assignment.md)

## 구현 범위

| 과제 항목 | 현재 구현 |
| --- | --- |
| 교육 소개·관리 | 랜딩·교육 3개의 상세·커리큘럼·대표 이미지·접수 가능 여부. 기본 admin 등록·편집 |
| 교육 신청 | 반응형 폼·주소 검색/직접 입력·Axios 비동기 제출·접수 상태 표시 |
| 신청 관리 | 반응형 백오피스와 기본 admin에서 조회·정정·상담·재연락·상태 관리. 변경 이력은 admin 조회. 신청 삭제 금지 |
| DRF API | 신청 화면용 교육정보 GET·신청 POST·검증·반복 제출 보호 |
| 자동 안내 | Q2 날짜별 검사·개발 모의 처리·운영 SES backend·선별 재시도 |

별도 백오피스는 신청·상담 관리와 이메일 처리 상태 조회에 집중하고 교육·계정·권한·이력 상세와 내부 task 기록은 Django admin에서 확인합니다. Google Spreadsheet 내보내기는 미구현입니다. 과제의 삭제 항목 대신 신청·상담 기록을 보존하고 완료·취소로 처리하는 정책을 선택했습니다. AWS는 SES·S3/CloudFront 설정을 구현했으며 실제 배포와 운영 static 서빙은 포함하지 않았습니다.

## 로컬 실행

**macOS/Linux의 Bash 기준**입니다. 저장소를 내려받은 뒤 루트 디렉터리에서 실행합니다.
준비 도구는 **[uv](https://docs.astral.sh/uv/getting-started/installation/)와 [Docker Compose v2](https://docs.docker.com/compose/install/)**입니다. Docker 엔진을 먼저 실행해 주세요. Python은 uv가 `.python-version`에 맞춰 준비합니다.
빌드된 CSS·JavaScript가 저장소에 포함되어 **Node.js·프론트 빌드·AWS 자격 증명 없이 실행**할 수 있습니다.

### 1. 의존성 설치

lockfile에 기록한 Python 패키지를 설치합니다. 별도의 가상환경 활성화는 필요하지 않습니다.

```bash
uv sync --locked
```

### 2. 개발 환경 변수 준비

아래 명령은 `.env.example`을 바탕으로 `.env`를 만들고 Django secret key·DB 비밀번호를 생성합니다. **이미 `.env`가 있으면 보존**하며 비밀값은 출력하지 않습니다.

```bash
uv run python - <<'PY'
from pathlib import Path
import secrets

path = Path(".env")
if not path.exists():
    content = Path(".env.example").read_text(encoding="utf-8")
    for key in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD"):
        content = content.replace(f"{key}=\n", f"{key}={secrets.token_urlsafe(32)}\n")
    path.write_text(content, encoding="utf-8")
print(".env 준비 완료: 기존 파일은 보존합니다.")
PY
```

Django와 Compose가 이 파일을 읽습니다. 로컬은 기본 `config.settings.dev`·`DJANGO_DEBUG=true`를 사용하며 AWS 항목은 비워 둡니다. 기존 DB volume이 있다면 기존 비밀번호를 유지합니다.

### 3. PostgreSQL 실행

DB만 컨테이너로 실행하고 연결 가능한 상태가 될 때까지 기다립니다. Django는 호스트에서 실행합니다.

```bash
docker compose up -d --wait db
```

기본 DB 포트는 `127.0.0.1:15432`입니다. 포트가 겹치면 `.env`의 `POSTGRES_PORT`를 변경합니다.

### 4. 테이블·샘플 교육 준비

`migrate`는 테이블을 만들고, `seed_educations`는 교육 3개와 로컬 이미지를 준비합니다. 초기 데이터 명령은 반복해도 기존 교육을 덮어쓰지 않습니다. 프로젝트의 migration은 빈 DB에 적용하는 `src/education/migrations/0001_initial.py` 하나입니다. 이전 개발 이력을 적용한 DB의 처리와 관리자 계정 준비는 [초기 migration 안내](docs/guides/operations.md#초기-migration과-개발-db-재생성)를 확인하세요.

```bash
uv run python src/manage.py migrate --noinput
uv run python src/manage.py seed_educations
uv run python src/manage.py check
```

### 5. 자동 안내 스케줄 등록

연락 가능 날짜가 된 신청을 **5분마다 검사하는 스케줄을 DB에 등록**합니다. 반복해도 중복 등록되지 않습니다. 이 명령이 worker를 실행하거나 메일을 보내지는 않습니다.

```bash
uv run python src/manage.py configure_background_tasks
```

### 6. 웹 서버·worker 실행

**터미널 1 — 웹 페이지와 API:**

```bash
uv run python src/manage.py runserver 127.0.0.1:8000
```

**터미널 2 — 같은 저장소 루트에서 자동 안내·이미지 정리 실행:**

```bash
uv run python src/manage.py qcluster
```

`qcluster`에 scheduler와 worker가 함께 포함됩니다. Redis나 별도 Beat 프로세스는 필요하지 않습니다. 웹 서버만 실행해도 신청은 저장되지만 안내와 이미지 정리는 worker가 있어야 처리됩니다.

## 실행 후 확인

1. [랜딩](http://127.0.0.1:8000/)에서 교육 3개를 확인하고 상세 페이지로 이동합니다.
2. **상담 신청**에서 이름·이메일·주소·오늘 이후 연락 가능 날짜를 입력합니다. 주소 검색을 사용할 수 없으면 직접 입력할 수 있습니다.
3. 제출 후 새로고침 없이 **신청 상태: 접수**와 접수 식별자가 표시되는지 확인합니다.
4. 자동 안내 처리 현황은 아래 명령으로 확인합니다. 개발은 실제 이메일을 보내지 않고 처리 완료를 `simulated`로 기록합니다.

```bash
uv run python src/manage.py notification_status
```

안내 대상은 **연락 가능 날짜의 한국 시각 09시부터**이며 다음 5분 검사와 큐 대기 후 처리됩니다. 오늘을 선택해도 09시 전이면 대기합니다. 즉시 확인용 자동 테스트와 API·장애 재현 방법은 [기능 검증 가이드](docs/guides/verification.md)에 있습니다.

`uv run python src/manage.py createsuperuser`로 관리자를 만든 뒤 [admin](http://127.0.0.1:8000/admin/)에서 교육·신청·상담을 관리합니다. 교육 목표·추천 대상은 줄 단위 텍스트로, 커리큘럼은 교시별 폼으로 편집하여 JSON을 직접 입력하지 않습니다. 신청 목록은 검색·상태/교육/날짜·재연락 필터를 제공하며 상세에서 정보 정정·상담 추가·변경 이력을 확인합니다. 완료·취소해도 기록은 남습니다. 자동 안내·발송 시도·공유 예산은 조회 전용이고 Q2 메뉴도 유지합니다. 권한과 상세 절차는 [관리 기능 확인](docs/guides/verification.md#관리-기능-확인)을 참고하세요.

종료할 때는 웹 서버·qcluster에서 `Ctrl+C`를 누르고 worker의 처리·결과 저장이 끝날 때까지 기다린 뒤 `docker compose down`으로 DB를 중지합니다. DB volume은 삭제하지 않습니다.

### 담당자용 백오피스

같은 관리자 계정으로 [백오피스](http://127.0.0.1:8000/backoffice/)와 [Django admin](http://127.0.0.1:8000/admin/)을 확인할 수 있습니다. 계정은 위 `createsuperuser` 명령으로 준비합니다. 로그인·로그아웃 상태를 공유하므로 한쪽에서 로그아웃하면 다른 화면에서도 재로그인이 필요합니다.

백오피스는 이름·이메일 검색, 교육·상태·재연락 필터와 페이지네이션, 신청 정정·상태·일정 변경, 상담 조회·추가를 제공합니다. 활성 staff와 모델별 권한을 모두 검사하며 superuser는 바로 확인할 수 있습니다. 신청 변경 권한과 상담 추가 권한이 있으면 기본 해제된 **상담 기록도 추가**를 선택해 함께 저장합니다. 상담 추가만 가능한 담당자는 신청은 읽기 전용으로 보고 **상담 추가**로 저장합니다. 상담 정정에는 상담 조회 권한도 필요합니다.

페이지 이동·검색은 GET, 로그인·로그아웃·신청/상담 저장은 일반 POST입니다. 이메일 조회 권한이 있으면 상세의 **상태 새로고침**이 Ajax로 이메일 영역만 갱신하여 작성 중인 입력을 유지합니다. 자동 polling·재발송·task 관리 화면은 제공하지 않습니다. 일반 저장의 세션 만료·CSRF 실패는 저장 없이 안내하며 작성 내용 자동 복구는 지원하지 않습니다. [백오피스 확인 절차](docs/guides/verification.md#백오피스-확인)를 참고하세요.

## 주요 설계 의도

```mermaid
flowchart LR
    A["교육 소개"] --> B["상담 신청 POST"]
    B --> C["신청·안내 대상 함께 저장"]
    C --> D["접수 결과 표시"]
    C --> E["Q2 5분 검사"]
    E --> F["건별 상담 안내 이메일"]
    F --> G["개발: 모의 완료"]
    F -.-> H["운영 설정: SES 접수"]
```

| 기능·선택 | 의도 |
| --- | --- |
| Templates·Tailwind·Axios | 단일 Django 서버에서 반응형 화면과 비동기 신청을 제공하고 별도 프론트 서버를 줄였습니다. |
| 교육정보 GET·신청 POST | GET은 선택 교육 안내에 사용하고 신청 개인정보 조회는 공개하지 않았습니다. |
| 제출 UUID·DB 고유 제약 | 응답 유실 후 같은 입력·ID로 재시도해도 접수와 안내 대상을 중복 생성하지 않습니다. |
| Q2·PostgreSQL 기본 큐 | 기존 DB를 활용해 별도 Redis 없이 날짜별 안내와 이미지 정리를 요청 처리에서 분리했습니다. |
| 발송 시도 기록·처리권 | 동시 발송을 제어하고 미접수가 확실한 오류만 재시도합니다. 결과 불명은 `unknown`으로 보존해 자동 재발송을 막습니다. |
| 비동기 이미지 정리 | 교육 변경과 큐 등록을 함께 commit하고 실행 시 참조를 재확인해 공유·재연결 파일을 보호합니다. |

SES 접수 성공은 실제 수신함 도착을 의미하지 않습니다. 외부 메일의 정확히 한 번 전달은 보장하지 않으며 SNS·웹훅·반송 확인은 후속 범위입니다. 상세 동작과 운영 준비는 [운영 가이드](docs/guides/operations.md)에 있습니다.

## 기술 스택·폴더 구조

Python 3.14 · Django 6.1.2 · DRF · PostgreSQL 18.6/Psycopg 3 · Tailwind CSS/esbuild · Axios 1.20.0 · Kakao 우편번호 검색 · Django Q2 1.11.1 · django-simple-history 3.13.0 · django-ses 4.8.2 · uv/Ruff를 사용합니다. 설치 조합은 `uv.lock`·`package-lock.json`으로 관리합니다.

```text
src/
    config/             # base/dev/prod 설정·프로젝트 진입점
    education/          # 모델·DRF API·페이지·관리 명령·테스트
        forms/          # 교육·신청·상담별 admin 입력 폼
        services/       # 신청 변경 검증·신청/이력/안내의 transaction 저장
        tasks/          # Q2 진입점·메일 처리 단계·이미지 정리
        migrations/     # 전체 모델을 생성하는 0001_initial.py
    templates/          # 공통 layout·교육/신청 화면·메일 본문·admin 위젯
    static/             # 빌드 CSS·Axios 포함 JS·source map·라이선스 고지
presets/education/      # 교육 3개의 초기 데이터·이미지 원본
frontend/              # 입력 CSS·직접 편집하는 JavaScript
    entries/            # 페이지·공통 기능별 JavaScript 진입 파일
docs/guides/            # 검토자를 위한 기능 검증·운영 설명
openspec/               # 변경 명세·설계·작업 기록
```

화면 자산을 수정하는 개발자는 `npm ci` 후 `npm run build` 한 번으로 CSS·JavaScript를 생성합니다. [개발용 빌드·변경 감시](docs/guides/operations.md#로컬-문제-해결화면-자산-수정)를 참고하세요.

## 자동 검증

앞의 환경·DB 준비 후 실행합니다. 별도 PostgreSQL 테스트 DB·임시 미디어를 사용하며 실제 이메일·AWS 호출은 없습니다.

```bash
uv run python src/manage.py test education
uv run python src/manage.py makemigrations --check --dry-run
uv run ruff check .
uv run ruff format --check .
```

2026-10-22 Windows에서 **141개 테스트**를 통과했습니다. 백오피스 권한·신청/상담 저장·DB 오류 rollback·이메일 부분 조회 17개와 기존 신청·상담 보존·변경 이력·교육 편집 폼·동시 제출·발송 처리권·기존 task 경로 호환·실제 qcluster 종료/복구를 포함합니다. macOS/Linux 전체 실행·모바일 실기기·AWS 실발송은 미검증입니다. [검증 범위와 한계](docs/guides/verification.md#검증-기록과-한계)를 별도로 기록했습니다.

## AI 도구 활용·추가 문서

Codex로 구현·테스트·문서 정리를 보조했습니다. OpenSpec으로 변경 의도와 작업을 관리하고, Django skill·ponytail을 코딩 기준과 과도한 추상화 방지에 활용했습니다. GitNexus는 코드 인덱스 관리에 사용했습니다. 최종 범위와 검증 결과는 이 저장소의 코드·테스트·문서에 기록했습니다.

- [기능 검증 가이드](docs/guides/verification.md): 기능별 예상 결과·API 계약·장애 재현·콘텐츠 출처
- [운영 가이드](docs/guides/operations.md): 이메일·이미지 처리 정책·AWS 설정·문제 해결
- [문서 안내](docs/README.md): 과제 검토 자료와 개발·유지보수 거버넌스 구분
