# Proposal

## Why

현재 프로젝트는 관리자 로그인만 제공하므로 교육을 탐색할 사용자 화면이 필요하다. 히어로스쿨 교육 3개의 소개 화면과 고정 프리셋을 제공하여 평가자도 동일한 초기 콘텐츠로 프로젝트를 실행할 수 있게 한다.

## What Changes

- `/`에 서비스 소개와 교육 카드가 있는 랜딩을, `/educations/<slug>/`에 교육 상세를 추가한다.
- 프롬프트 히어로, 감정탐험 히어로, 관계 히어로의 공개 정보를 바탕으로 교육명·한 줄 소개·이미지·목표·추천대상·시수별 커리큘럼을 제공한다.
- Django Templates와 Tailwind CSS로 교육 소개 목적의 반응형 레이아웃을 구현한다. 빌드 CSS와 초기 이미지 원본을 저장소에 포함하고 교육 이미지는 static이 아닌 미디어 저장소에서 제공한다.
- Django 설정을 `base.py`·`dev.py`·`prod.py`로 분리한다. 개발은 로컬 미디어, 운영은 S3 저장·CloudFront 제공을 사용하며 표준 `DJANGO_SETTINGS_MODULE`로 선택한다.
- uv 공통 실행 의존성을 유지하고 `prod`·`dev` 그룹만 추가·구성한다. 기본 `dev`는 `prod`를 포함해 개발에 필요한 패키지를 설치하고, 운영은 공통 의존성과 `prod`만 설치한다.
- PostgreSQL 교육 모델과 고정 데이터 프리셋, 중복 생성과 기존 데이터 덮어쓰기가 없는 초기화 명령을 추가한다.
- 아키텍처·개발 규약에 Tailwind, 의존성 그룹, 설정 분리와 미디어 저장소 정책을 반영하고 README와 `.env.example`에 실행 모드·초기 데이터 설정 절차를 제공한다.
- 이번 범위에서 신청 폼·신청 API·회원가입·로그인 화면·교육 관리 전용 UI·실시간 크롤링·실제 AWS 리소스 생성과 배포는 제외한다. 신청 기능은 후속 MVP이며 별도 관리자 신청 목록, Google Spreadsheet 내보내기, AWS 배포 구성은 MVP 이후 예정 사항으로 유지한다. S3·CloudFront 연동 설정과 설치 구조는 이번 범위에 포함한다. 자동 메일은 기존의 미결정 상태를 유지한다.

## Capabilities

### New Capabilities

- `education-catalog`: 공개 랜딩·교육 상세, 반응형 교육 콘텐츠 탐색과 환경에 맞는 이미지 제공.
- `education-presets`: 히어로스쿨 교육 3개의 고정 데이터와 선택된 미디어 저장소를 사용하는 안전한 초기 설정.

### Modified Capabilities

없음. 현재 등록된 기본 명세는 없다.

## Impact

- `src/education/`의 모델·migration·view·URL·template·static·프리셋 이미지·관리 명령·테스트와 `src/config/urls.py`가 구현 대상이다.
- `src/config/settings.py`를 settings 패키지로 전환하며 manage.py·ASGI·WSGI 진입점과 기존 설정 테스트를 동기화한다. `.env.example`, `pyproject.toml`, `uv.lock`과 미디어 Git 제외 설정이 영향을 받는다.
- Tailwind CLI 개발 의존성·lockfile·빌드 명령을 추가한다. 로컬 평가자의 Django 실행에는 Node.js나 외부 CDN이 필요하지 않게 한다.
- 운영 전용 저장소 의존성은 `django-storages[s3]`를 사용하고 기본 로컬 개발 설치에도 포함한다. 저장소는 선택한 settings 모듈에서 구성하며 실행 중 패키지를 설치하지 않는다.
- `docs/architecture.md`, `docs/development.md`, `README.md`를 동기화한다. 로컬 AGENTS 관리 블록과 template managed 파일은 변경하지 않는다.
- 공개 GET 페이지와 교육 테이블이 추가된다. 기존 `/admin/`과 인증·인가 경계는 유지하며 개인정보는 수집하지 않는다.
