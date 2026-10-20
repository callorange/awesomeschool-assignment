# Proposal

## Why

현재 저장소에는 과제 원문과 도구 설정만 있어 Django 실행, PostgreSQL 연결, 의존성 설치 및 검증을 재현할 기반이 없다. 4일 과제의 핵심인 교육 소개 → 신청 접수 → 신청 관리 구현에 집중할 수 있도록 프로젝트 구조와 개발 규약을 먼저 마련한다.

## What Changes

- Python 3.14, Django 6.1.2, DRF, Psycopg 3, PostgreSQL 18.6을 사용하는 단일 Django 프로젝트의 초기 실행 환경을 구성한다.
- uv의 비패키지 방식으로 `pyproject.toml`과 `uv.lock`을 관리하고, Ruff와 Django 기본 테스트 도구로 검증 방식을 통일한다. Django 프로젝트 자체의 배포 패키지는 빌드·설치하지 않는다.
- `src/config/`에 Django 설정과 진입점, `src/education/`에 향후 교육·신청 기능을 담을 앱 골격을 배치한다. 화면은 Django Templates, CSS, JavaScript `fetch`를 사용하는 방향으로 기록한다.
- 로컬 PostgreSQL 실행용 Compose와 `.env.example`을 제공하고, 환경 변수로 Django와 DB 설정을 주입한다.
- README와 `docs/architecture.md`에 실행·검증 절차, 구조, 기술 선택 이유, 현재 구현 범위 및 후속 작업을 기록한다.
- `AGENTS.md`의 Project Rules와 `openspec/config.yaml`에 프로젝트 고유의 개발 규약과 OpenSpec 지침을 반영한다. 템플릿 managed 영역과 설치 파일은 변경하지 않는다.
- 별도 관리자 목록 화면, Google Spreadsheet 내보내기, AWS 계획·배포 구성, AI 도구 활용 기록은 MVP 이후 구현 예정 사항으로 계속 관리한다.
- 교육 소개 화면, 신청 모델·폼·API·CRUD는 후속 기능 change에서 구현한다. 자동 안내 메일의 MVP 포함 여부도 해당 기능 기획에서 결정하며 이번 초기 구성에는 포함하지 않는다.

## Capabilities

### New Capabilities

없음. 이번 변경은 개발 환경·도구·문서 초기 구성으로, 교육 신청 시스템의 사용자 기능을 새로 정의하지 않는다. `.openspec.yaml`에 `skip_specs: true`를 선언하며 delta spec을 만들지 않는다.

### Modified Capabilities

없음. 현재 등록된 main spec이 없다.

## Impact

- 추가 대상: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `compose.yaml`, `src/`, `README.md`, `docs/architecture.md`.
- 수정 대상: `openspec/config.yaml`, `AGENTS.md`의 Project Rules. 과제 원문, 기존 ignore 설정 및 도구 설치 파일은 유지한다.
- 런타임 직접 의존성: Django, `djangorestframework`, `psycopg[binary]`. 개발 직접 의존성: Ruff. 테스트는 Django와 DRF 내장 도구를 사용한다.
- 기존 서비스 코드·공개 API·업무 DB가 없으므로 기존 계약이나 데이터의 변환은 없다. Django 내장 앱의 초기 migration은 새 로컬 개발 DB에만 적용한다.
- 완료 증거는 lockfile 기반 설치, Django system check, PostgreSQL 연결·기본 migration, 초기 smoke test, Ruff 검사 및 문서와 명령의 일치 여부다. 운영 배포와 실제 외부 서비스 연동은 수행하지 않는다.
