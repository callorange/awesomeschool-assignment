# 개발 규약

이 문서는 개발 절차, 검증 기준과 Git 정책의 원본입니다. 구조·기술 선택은 [아키텍처](architecture.md), 실제 실행 명령과 현재 구현 범위는 [프로젝트 README](../README.md)를 따릅니다.

## 검증과 코드 문서화

변경의 직접 영향을 받는 가장 좁은 검사부터 수행합니다. 공통 설정·의존성·여러 기능에 걸친 변경은 README의 Django check, migration 변경 누락 검사, `test education`, Ruff lint·format 검사로 검증합니다. 문서만 바뀌면 링크·경로·명령과 구현의 정합성을 확인하며 동작 테스트를 일괄 재실행하지 않습니다. 테스트는 PostgreSQL의 별도 테스트 DB를 사용합니다. 실제 `.env`와 격리한 파일 로딩·환경 변수 우선순위·설정 오류·파싱, 실제 DB 쿼리, 관리자 로그인 화면을 확인하고, 정적 파일은 실제 개발 서버에서 별도로 확인합니다. 실패를 코드 오류와 환경 문제로 구분하며 미검증 항목을 성공으로 기록하지 않습니다.

Ruff는 Python 3.14를 대상으로 프로젝트 소유 코드만 검사합니다. 에이전트 스킬·template managed 파일과 도구 캐시는 검사·자동 수정하지 않습니다. 새 주석과 docstring은 한국어로 작성하되 Django가 생성한 기존 설명은 유지합니다. 코드만으로 드러나지 않는 책임·입력 구조·반환·오류·중요한 side effect를 Google-style docstring으로 설명하고, 주석에는 정책과 제약의 이유를 기록합니다. 자명한 wrapper나 framework override마다 설명을 반복하지 않습니다. 계약 변경 시 관련 설명도 함께 갱신합니다.

## 환경별 설치와 설정 검증

- 기본 `uv sync --locked`는 공통+dev+prod 의존성을 설치합니다. 운영은 `uv sync --locked --no-default-groups --group prod`로 공통+prod만 설치하며 Ruff 등 개발 도구가 없어야 합니다. 운영 실행은 직접 가상환경 실행 또는 `uv run --no-sync`로 기존 설치를 유지합니다.
- `config.settings.dev`와 `config.settings.prod`를 독립된 설정 패키지로 로딩하여 .env 경로·환경 변수 우선·누락 및 빈 값 거부·DEBUG 계약을 검증합니다. 진입점은 이미 지정한 설정 모듈을 보존해야 합니다.
- 로컬 미디어 검증은 임시 디렉터리를 사용합니다. 운영 백엔드 선택·CloudFront URL·설정 오류는 AWS 호출 없이 확인합니다. 실제 AWS 쓰기와 CloudFront 응답 검증은 별도 명시적 opt-in으로 수행하며 기본 테스트에 포함하지 않습니다.

## Tailwind CSS와 화면 검증

- 프로젝트 template와 static은 `src/templates/`와 `src/static/`에 통합하고, template는 기능별 하위 폴더로 구분합니다. 공통 layout은 `src/templates/base.html`을 사용합니다. 앱 내부에 프로젝트 소유 template·static 폴더를 새로 분산하지 않습니다.
- 스타일은 현재의 npm 기반 Tailwind CSS CLI로 작성합니다. `frontend/styles.css`가 입력이고 `src/static/css/site.css`가 생성물입니다. 클래스는 template에 완전한 문자열로 작성합니다.
- 개발 도구와 배포 자산 의존성은 `npm ci`로 설치합니다. `npm run build:css`로 빌드하고 `npm run watch:css`로 변경을 감시합니다. `npm run vendor:axios`로 lockfile에 고정한 Axios ESM 파일·source map·라이선스를 `src/static/vendor/axios/`에 복사합니다. 생성 자산·package-lock·관련 template를 같은 작업에 포함하며 생성 파일을 직접 편집하지 않습니다.
- 로컬·평가 실행은 저장소의 CSS·Axios 자산을 사용하며 Node.js·외부 Axios CDN·Tailwind CDN·외부 글꼴을 요구하지 않습니다. Tailwind는 npm 개발 도구이고 Axios는 브라우저 배포 자산 의존성입니다. 둘 다 Django 운영 서버에서 npm 설치·실행을 요구하지 않습니다.
- 랜딩·교육 상세·신청을 360px·390px·768px·1280px에서 확인합니다. 카드 1·2·3열, 본문·커리큘럼·폼 잘림과 가로 스크롤, 이미지 비율, 키보드 포커스와 터치 영역을 검증합니다. 반응형 검증을 HTML 렌더링 테스트로 대체하지 않고 Android Chrome·iOS Safari 실기기 확인 여부를 별도로 기록합니다.
- 빌드 재현성은 같은 lockfile로 CSS를 재빌드해 산출물의 hash를 비교합니다. CSS와 이미지의 HTTP 200도 실제 서버에서 확인합니다.

## 프리셋 변경과 검증

- 초기 데이터 JSON과 이미지 원본은 `presets/education/`에서 함께 관리하고 출처 URL·수집일·요약 편집 여부를 유지합니다. 초기화 명령은 앱의 management command에 둡니다.
- 원본·로딩 경로·초기화 명령을 바꾸면 실제 테스트 DB와 임시 미디어에서 `uv run python src/manage.py test education.tests.test_presets education.tests.test_pages`로 초기화·재실행 보존·실패 시 롤백·화면 렌더링을 검증합니다. 원본 위치만 옮길 때는 파일 내용의 보존도 확인합니다.
- 프리셋 변경만으로 기존 DB 레코드와 이미지가 갱신되지는 않습니다. 검증은 격리된 테스트 DB에서 수행하며, 확인을 위해 개발·공유 데이터나 저장소 파일을 지우지 않습니다.

## Git Workflow

GitHub Flow의 기준 브랜치는 `main`, 작업 브랜치는 `feature/<NNN>-<work-name>`입니다. 계획과 구현은 같은 브랜치에서 별도 커밋으로 관리하고 검증 후 PR로 검토합니다. `feature/*`를 `main`에 병합할 때는 `git merge --no-ff <feature-branch>`로 merge commit을 남깁니다. GitHub PR에서는 `Create a merge commit`을 사용합니다. Conventional Commits의 영어 type과 한국어 제목을 사용합니다.

작업 브랜치는 `main`에서 생성하며 OpenSpec 사용 여부와 관계없이 `feature/<NNN>-<work-name>` 형식을 사용합니다. `<work-name>`은 작업을 설명하는 kebab-case 이름입니다. `NNN`은 작업 생성 순서에 따른 세 자리 순번(001부터)이며 문자 코드는 붙이지 않습니다. 새 번호는 기존 브랜치·Git 이력·OpenSpec 기록에서 사용한 최대 번호의 다음 값으로 정하고, 삭제한 브랜치의 번호는 재사용하지 않습니다. OpenSpec change가 있으면 `<work-name>`을 해당 change 이름과 일치시키고 change 이름에는 번호를 붙이지 않습니다. OpenSpec 없이 진행하는 개별 작업은 작업 내용을 기준으로 `<work-name>`을 정하며 같은 번호 순서를 사용합니다. 예를 들어 change `improve-education-model`의 브랜치는 `feature/004-improve-education-model`입니다. 확정한 계획을 먼저 커밋하고 구현·검증 결과는 별도 커밋으로 남깁니다. 커밋 type은 브랜치 접두사와 관계없이 변경 목적에 맞게 선택합니다. 병합을 확인한 뒤 작업 브랜치를 정리합니다.

이 정책만으로 commit·push·PR 생성·병합·브랜치 삭제를 자동 승인하지 않습니다. 해당 작업은 사용자의 직접 요청 또는 이미 승인된 범위에서 수행합니다.

## OpenSpec 기록

OpenSpec change 문서는 해당 변경의 제안·설계·작업 및 결정 당시의 기록입니다. 완료된 archive는 이후 공통 정책이 바뀌어도 일괄 수정하지 않습니다. 현재 공통 규약은 [문서 안내](README.md)가 연결한 주제별 문서를 따릅니다. 별도 constitution이나 custom schema는 만들지 않습니다.
