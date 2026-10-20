# Tasks

## 1. 환경별 설정과 의존성

- [ ] 1.1 공통 실행 의존성을 유지하고 prod 그룹에 호환 가능한 django-storages[s3], dev 그룹에 prod 포함과 Ruff를 선언하며 uv.lock을 갱신한다. 임시 환경에서 `uv sync --locked`와 `uv sync --locked --no-default-groups --group prod`를 각각 검증하여 dev에는 전체 개발 패키지, prod에는 S3 의존성이 있고 Ruff는 없는지 확인한다. 공개 classifier로만 호환성을 추측하지 않고 실제 Python·Django 조합의 설치와 백엔드 동작을 검증한다.
- [ ] 1.2 settings.py를 base.py·dev.py·prod.py 패키지로 분리하고 manage.py·ASGI·WSGI의 기본값과 문서 주석을 동기화한다. 기존 test_settings.py의 단일 파일 복사 방식을 패키지 격리 로딩으로 변경하여 저장소 루트 .env 탐색, 프로세스 환경 우선, 필수값·빈 값 거부, 지역화와 DEBUG 파싱을 계속 검증한다. 기본 dev 선택과 명시적 DJANGO_SETTINGS_MODULE·관리 명령 --settings 선택도 확인한다.
- [ ] 1.3 dev의 FileSystemStorage·MEDIA_ROOT·MEDIA_URL과 DEBUG 전용 미디어 URL, prod의 S3Storage·CloudFront OPTIONS를 구성한다. 임시 미디어로 로컬 저장·URL을 검사하고 외부 연결 없이 prod 백엔드 선택·상대 이름 기반 HTTPS CloudFront URL·필수 설정 오류·DEBUG 활성화 거부·로컬 fallback 없음·개발 미디어 URL 미등록을 테스트한다. dev에서는 AWS 패키지를 로딩하거나 credential을 조회하지 않는지도 확인한다.
- [ ] 1.4 `.env.example`, README, docs/architecture.md, docs/development.md에 두 의존성 그룹·settings 선택·로컬 미디어·운영 S3/CloudFront OAC 전제와 검증 절차를 반영하고 생성 media 디렉터리를 Git에서 제외한다. README의 운영 설치 후 직접 실행 또는 `uv run --no-sync` 절차가 dev 그룹을 재설치하지 않는지 확인한다. 환경 변수 누락 오류에 비밀값이 노출되지 않고 기본 테스트가 AWS에 접속하지 않는지 검사한다.

## 2. 교육 데이터와 초기 설정

- [ ] 2.1 히어로스쿨 공식 상세 페이지에서 지정한 교육 3개의 소개·목표·대상·시수별 커리큘럼과 대표 이미지를 수집하여 data/ 아래 JSON 프리셋과 이미지 원본으로 저장한다. 원문 URL·이미지 URL·실제 수집일·요약 편집 여부를 기록하고, 원문 대조와 이미지 열기로 교육별 데이터가 정확히 대응하는지 확인한다.
- [ ] 2.2 기존 education 앱에 설계의 Education 모델·이미지 FileField와 신규 테이블 migration을 추가한다. 실제 PostgreSQL에서 저장·조회와 slug 고유성, 이미지에 저장소 상대 이름만 저장됨을 테스트하고 `sqlmigrate`로 기존 테이블을 변경하지 않는지 확인한다. docs/architecture.md의 앱·데이터 구조를 동기화한다.
- [ ] 2.3 seed_educations에서 전체 프리셋·이미지 원본을 사전 검증하고 선택한 Storage에 파일을 저장하며 transaction과 slug 기준으로 누락 교육만 생성한다. 실제 테스트 DB와 임시 로컬 미디어에서 첫 실행·재실행·수정 및 별도 교육·이미지 보존·부분 초기화 보충·잘못된 입력의 무쓰기 실패를 검증한다. 외부 저장소 fake로 저장 실패 시 DB 롤백·남은 파일 보고·재실행 시 재사용을 검증하며 DB 원자성을 mock으로 우회하지 않는다.
- [ ] 2.4 README에 평가자용 dev migration → seed → runserver와 재실행 보존 정책·콘텐츠 출처를 설명한다. 운영 seed는 준비된 S3에 쓰는 명시적 작업이며 단순 settings 전환으로 기존 로컬 파일이 복사되지 않음을 기록한다. 격리된 개발 DB·미디어에서 문서 명령으로 교육과 이미지 3개를 설정하고 재실행 시 보존되는지 확인한다.

## 3. Tailwind 빌드와 공유 규약

- [ ] 3.1 Tailwind CSS와 CLI의 개발용 npm 의존성·lockfile, 입력 CSS, build:css·watch:css, template 탐색 범위를 설정하고 빌드 CSS를 앱 static 경로에 포함한다. `npm ci`와 `npm run build:css` 성공 및 출력 파일 생성을 확인하고 node_modules가 Git에서 제외되는지 검증한다.
- [ ] 3.2 docs/architecture.md에 Tailwind 선택과 프론트 개발 도구·런타임 구분을, docs/development.md에 CSS 원본·생성물 동기화와 반응형 검증 기준을 반영한다. README에는 개발자 빌드·watch 절차를 추가하고 기존 별도 프론트 빌드 없음 설명과의 충돌을 해소한다. 문서 간 링크와 실행 명령을 대조하고 template managed 파일에 변경이 없는지 확인한다.

## 4. 랜딩과 교육 상세 화면

- [ ] 4.1 공통 template, 랜딩 view·URL, 서비스 소개와 교육 카드를 구현한다. Django 테스트로 익명 HTTP 200·교육 3개와 상세 링크·정렬·빈 목록 안내를 검증하고 기존 관리자 로그인 smoke test도 통과시킨다.
- [ ] 4.2 교육 상세 view·URL·template에 제목·소개·이미지 .url·목표·대상·시수별 커리큘럼·출처·랜딩 복귀 링크를 구현한다. 실제 DB 렌더링·모든 시수의 교시 순서·없는 slug의 404·본문 escaping을 테스트하고 동일 template가 dev 로컬 URL과 prod CloudFront URL을 출력하는지 외부 연결 없이 확인한다.
- [ ] 4.3 Tailwind로 모바일 1열·태블릿 2열·데스크톱 3열 카드와 상세 반응형 배치를 완성한다. 360px·768px·1280px에서 랜딩과 교육 상세 3개를 확인하여 겹침·잘림·페이지 가로 스크롤이 없고 키보드 포커스·주요 터치 영역·이미지 대체 텍스트가 제공됨을 기록한다.
- [ ] 4.4 화면 변경 후 CSS를 다시 빌드하고 README의 현재 구현 상태·화면 경로·AI 도구 활용 내역을 실제 결과로 갱신한다. Django static 탐색과 dev 브라우저에서 CSS·미디어 이미지 HTTP 200, 정상 스타일 표시, 내부 링크 이동을 확인한다.

## 5. 통합 재현 검증

- [ ] 5.1 README의 Django check, migration 변경 누락 검사, `test education`, Ruff lint·format 검사를 dev 환경에서 실행한다. prod 환경에서는 명시적 prod settings로 DB·AWS 접속 없는 설정 검사를 수행하고 실제 설치 집합도 확인한다. regression·기존 실패·환경 제약을 구분하여 기록한다.
- [ ] 5.2 동일 lockfile로 CSS를 재빌드하여 저장소 산출물과 일치하는지 확인한다. dev 프리셋 설정 후 외부 사이트·CDN 연결을 차단한 브라우저에서 랜딩과 상세 3개의 콘텐츠·CSS·미디어 이미지가 모두 로컬에서 제공되는지 검증한다. 실제 S3 업로드·CloudFront 응답 검증은 별도 opt-in으로 구분하고 실행하지 않았으면 미검증으로 보고한다.
- [ ] 5.3 코드·문서·프리셋·미디어·CSS·settings·의존성 그룹이 명세와 일치하는지 diff를 확인하고 `openspec validate add-front-end --strict`를 통과시킨다. 실제 검증 결과가 있는 항목만 완료 처리하고 미완료 이미지 수집·반응형 검사·실제 AWS 연결을 명시한다.
