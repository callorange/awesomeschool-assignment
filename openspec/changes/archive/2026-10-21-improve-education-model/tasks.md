# Tasks

## 1. 교육 모델과 공통 검증

- [x] 1.1 Education에 운영 방식 TextChoices·operation_type·operation_note·is_accepting_inquiries를 추가하고 정상 값의 영속화·기본값·잘못된 운영 방식의 full_clean() 오류를 모델 테스트로 확인한다.
- [x] 1.2 기존 문자열 목록·커리큘럼 검증을 module-level JSONField validator로 옮긴다. 정상 프리셋, 빈 목록·공백·잘못된 타입·누락 키·중복/boolean 시수·교시 수와 순서 오류를 full_clean()에서 필드별 ValidationError로 확인하며 save() 자동 검증은 추가하지 않는다.
- [x] 1.3 새 migration을 생성하고 기존 migration은 유지한다. sqlmigrate로 SQL을 확인하고 격리된 PostgreSQL migration 테스트에서 기존 PK·콘텐츠·미디어·출처·정렬 보존 및 새 기본값을 검증한다. uv run python src/manage.py test education.tests.test_models와 새 migration 테스트를 실행한다.
- [x] 1.4 docs/architecture.md에 세 필드·JSON 검증 경계·직접 ORM 쓰기의 한계를 반영하고 모델 docstring과 실제 계약의 일치를 확인한다.

## 2. 프리셋과 초기화 계약

- [x] 2.1 프리셋 3개에 코치 출강·접수 활성·상담 후 일정과 조건을 협의한다는 안내를 명시하고 editorial_note로 과제용 안내를 구별한다. 기존 이미지·커리큘럼·출처와 수집일이 유지되는지 확인하고 신규 설정값을 프리셋 테스트로 검증한다.
- [x] 2.2 seed_educations의 full_clean(validate_unique=False)에서 공통 콘텐츠 검증을 사용하고 중복 private 검사를 제거한다. 이미지 사전 검사·DB transaction·파일 재사용은 유지하고 잘못된 운영 방식과 콘텐츠가 DB·미디어 쓰기 전에 거부되는지 테스트한다.
- [x] 2.3 수정한 운영 방식·진행 안내·접수 상태의 재실행 보존을 테스트하고 기존 저장 실패·롤백·파일 재사용 테스트를 유지한다. uv run python src/manage.py test education.tests.test_presets를 실행하고 README의 초기 데이터 설명과 기존 데이터 보존 정책을 동기화한다.

## 3. 공개 운영 안내

- [x] 3.1 상세 template에 운영 방식·선택적 진행 안내·접수 가능/중단 안내를 표시한다. 두 운영 방식·빈 안내·HTML escaping·접수 중단 시 랜딩/상세 접근 유지·가짜 신청 링크 부재를 페이지 테스트로 검증한다. uv run python src/manage.py test education.tests.test_pages를 실행한다.
- [x] 3.2 npm run build:css로 template 변경에 필요한 생성 CSS를 반영하고 360·768·1280px에서 운영 안내의 줄바꿈·잘림·기존 커리큘럼과 탐색을 확인한다. 같은 입력의 재빌드 hash 일치와 CSS·이미지 HTTP 200을 확인한다.
- [x] 3.3 README의 구현 상태·교육 신청을 상담 접수로 해석한 설계 의도·향후 신청 기능의 서버 접수 상태 검사 책임을 동기화한다. 신청·편집 기능이 구현된 것으로 서술하지 않았는지 코드와 비교한다.

## 4. 통합 검증

- [x] 4.1 로컬 DB 환경에서 uv run python src/manage.py check, uv run python src/manage.py makemigrations --check --dry-run, uv run python src/manage.py test education, uv run ruff check ., uv run ruff format --check .를 실행한다. 실패는 회귀·기존 실패·명령 오류·환경 문제로 구분하고 미검증 범위를 기록한다.
- [x] 4.2 최종 diff에서 기존 공개 URL·JSON 형태·미디어 참조 보존, 신규 모델/신청 경로/외부 연결 부재와 문서 정합성을 확인하고 OpenSpec validate --strict 통과를 확인한다.

## 5. 교육별 이미지 경로와 파일명

- [x] 5.1 교육별 images 경로와 일반 파일의 UUID upload_to callable을 추가하고 후속 필드 상태 migration을 생성한다. 같은 원본 이름의 다른 파일이 다른 키로 저장되고 기존 파일이 덮어쓰이지 않는지, Storage 반환 키가 반영되는지, 기존 키 조회·slug 변경 시 키 보존을 임시 Storage 테스트로 확인한다. sqlmigrate와 migration 누락 검사로 기존 데이터 이동이 없음을 확인하고 docs/architecture.md에 경로 정책을 반영한다.
- [x] 5.2 프리셋을 교육별 경로·SHA256 파일명으로 저장하도록 변경하되 기존 교육 참조 보존과 실패 잔여 파일 재사용을 유지한다. 신규 경로·기존 형식 키 보존·저장 실패 후 재실행·삭제 정리 후 재생성 테스트를 실제 테스트 DB와 임시 미디어에서 실행하고 README 초기화 설명을 동기화한다.

## 6. 이미지 삭제·교체 수명주기

- [x] 6.1 교육 단일·일괄 삭제 후 transaction.on_commit에서 다른 교육의 파일 참조를 재확인하고 미참조 파일만 해당 Storage로 정리하도록 signal을 등록한다. commit 전 보존·commit 후 삭제·rollback 보존·공유 파일 보존을 실제 transaction 테스트로 확인하고 모델·아키텍처 문서에 삭제 side effect를 기록한다.
- [x] 6.2 일반 모델 save()의 이미지 교체에서 이전 파일을 commit 후 정리하고 신규 이미지와 공유 파일을 보존한다. 같은 키·image를 제외한 update_fields·이미지 외 수정·교체 rollback·같은 transaction의 재연결을 테스트하며 QuerySet.update()/bulk_update() 우회 경계를 문서화한다.
- [x] 6.3 저장소 삭제 실패 시 대상 키와 오류를 기록하고 commit된 DB 결과와 다른 정리 처리를 유지한다. 실패를 주입해 로그·DB 상태·다른 callback 실행을 검증한다. 프리셋 원본·관련 없는 파일은 유지되는지 확인하고 README에 자동 정리 범위와 잔존 파일 가능성·전수 청소 제외를 명시한다.

## 7. 이미지 보완 통합 검증

- [x] 7.1 Django check·migration 변경 누락 검사·test education·Ruff lint/format·OpenSpec validate --strict를 실행한다. 새 키와 기존 키의 상세 렌더링 및 미디어 URL 계약을 확인하고 diff에서 기존 파일 일괄 이동·외부 AWS 호출·신청/편집 UI 추가가 없음을 확인한다. 아래 과거 결과와 구분하여 이미지 보완 검증 결과를 기록한다.

## 8. UUIDv7 고정 이미지 폴더

- [x] 8.1 media_id UUIDv7 필드와 저장 전 경로 생성을 추가하고 slug 변경·이미지 교체 후 폴더 고정, DB 고유성·편집 제외를 테스트한다.
- [x] 8.2 프리셋 고정 UUIDv7과 사전 검증을 추가하고 기존 교육 보존·실패 후 파일 재사용·잘못된 UUID 입력 무부작용을 테스트한다.
- [x] 8.3 2초 잠금 제한의 후속 migration으로 기존 행에 UUIDv7을 부여하고 기존 값·이미지 키 보존·역적용 후 재적용을 PostgreSQL에서 검증한다. SQL·migration 누락·전체 교육 테스트·Ruff·OpenSpec strict를 확인하고 README·아키텍처를 동기화한다.

## 9. 수집 기록 분리와 개발 migration 정리

아래 작업은 사용자가 승인한 DB 초기화와 migration 재생성으로 이전 단계의 데이터 보존·분할 migration 결정을 대체한다. 앞선 Verification Results는 변경 당시 검증 기록으로만 남긴다.

- [x] 9.1 수집 기록 4개 필드를 모델·상세에서 제거하고 JSON에만 보존한다. 초기화·모델 검증 입력과 테스트를 수정하고 관련 문서·명세를 동기화한다.
- [x] 9.2 0001을 유지하고 후속 파일을 삭제한 뒤 Django로 단일 0002를 생성한다. 프로젝트 DB 컨테이너·볼륨을 삭제 후 재생성하고 migration·프리셋 3개 생성·재실행 보존·DB 필드 및 이미지 내용 일치를 확인한다.
- [x] 9.3 전체 교육 테스트·Django check·migration 누락·SQL·Ruff·CSS 빌드·OpenSpec strict·diff를 검증한다. 기존 DB 업그레이드 호환성과 실제 AWS 검증을 주장하지 않는다.

## Verification Results

아래는 이미지 저장·수명주기 보완 전 기존 1~4단계의 검증 결과다. 5~7단계의 결과는 Image Verification Results에 별도로 기록한다.

- 2026-10-21: Django check 및 migration 변경 누락 검사 통과. `test education` 38개 통과, Ruff lint·format 통과.
- 모델·migration 테스트 7개, 프리셋 테스트 5개, 페이지 테스트 8개를 각 구현 단계에서 통과했다. 최종 검토에서 역 migration의 잠금 제한 실행 순서를 보완한 뒤 migration 테스트 1개와 Ruff 검사를 재실행하여 통과했다.
- 사용자가 승인한 `lock_timeout = '2s'`를 정방향·역방향 DDL 전에 적용했다. SQL 확인과 격리 PostgreSQL migration 테스트로 기존 필드와 새 기본값을 검증했다.
- 격리된 `test_awesomeschool_preview` DB와 임시 미디어로 실제 브라우저에서 360·768·1280px 랜딩·상세를 검증했다. 출강·코스웨어·접수 중단·빈 안내·줄바꿈·이미지 로딩·키보드 포커스와 가로 넘침 없음을 확인했다. CSS·이미지 HTTP 200을 확인하고 검증 서버·DB·미디어를 정리했다.
- CSS를 같은 입력으로 두 번 빌드한 SHA256이 일치했다: `F1DE3D3B38FEFF2E515388D9D3F92EF4BF88C20023319ED417494C197FAC22B5`.
- 로컬 dev 설정·loopback DB임을 검사한 뒤 migration을 적용했고 기존 교육 3개의 모든 기존 필드·이미지 참조가 보존됨을 비교했다. 기존 교육은 빈 진행 안내를 유지하며 프리셋으로 덮어쓰지 않았다.
- 변경 diff와 Django 검토 기준으로 모델·초기화·페이지·문서 계약을 점검했다. 신청·편집 UI, 운영 배포·AWS 연결, commit·push는 수행하지 않았다.

## Image Verification Results

- 2026-10-21: `test education` 전체 55개 통과. Django check·migration 누락 검사·Ruff lint/format·OpenSpec strict 검증 통과.
- 교육별 UUID 파일명·확장자 처리, 강제 UUID 충돌 시 Storage의 변경 이름 저장과 기존 파일 내용 보존, 기존 키·slug 변경의 무이동을 임시 Storage에서 검증했다.
- 프리셋 교육별 SHA256 경로·기존 형식 키 보존·실패 잔여 파일 재사용과 commit된 교육 삭제 후 파일 재생성을 검증했다. 기존 CloudFront 경로 고정 assertion은 실제 저장 키 기준으로 수정하고 신규·기존 키 렌더링을 확인했다. 실제 AWS 연결은 하지 않았다.
- 실제 PostgreSQL transaction에서 단일·일괄 삭제, commit 이전 보존·이후 정리, 삭제·교체 rollback, 공유 파일·동일 키·image 제외 저장·재연결 보존을 확인했다.
- 저장소 삭제 실패를 주입하여 로그에 키·예외 종류만 남고 예외 본문은 노출되지 않으며 commit된 DB 결과와 다른 정리 callback이 유지됨을 확인했다. 이미지 교체 실패 후 새 참조 유지와 프리셋 원본·관련 없는 파일 보존도 확인했다.
- `0003_alter_education_image`의 SQL이 no-op임을 확인했다. 로컬 dev·loopback DB임을 검사한 뒤 적용하고 기존 교육 3개의 모든 값과 이미지 키가 동일함을 비교했다. 기존 파일 일괄 이동·개발 데이터 삭제는 하지 않았다.
- 최종 diff와 Django 검토 기준으로 경로·signal 등록·공유 참조·transaction·문서의 계약을 점검했다. 이번 이미지 보완은 레이아웃을 변경하지 않아 브라우저 크기 검증을 반복하지 않았으며 새 키·기존 키의 페이지 렌더링과 Storage URL을 자동 테스트했다.
- 실패·rollback 새 파일과 프로세스 중단으로 잔존 파일이 생길 가능성은 유지된다. 전수 청소·정리 큐·운영 파일 삭제·commit·push는 실행하지 않았다.

## UUIDv7 Verification Results

- 2026-10-21: `test education` 전체 58개 통과. Django check·migration 누락 검사·Ruff lint/format·OpenSpec strict 검증 통과.
- 저장 전 UUIDv7 생성과 DB 조회 없는 경로 결정, slug 변경·이미지 교체 후 같은 UUID 폴더 유지, media_id 고유성과 편집 제외를 검증했다. 일반 파일의 UUIDv4 파일명과 프리셋 SHA256 파일명은 유지했다.
- 프리셋 고정 UUIDv7의 누락·형식·버전·중복 오류가 DB·미디어 쓰기 전에 거부되는지 확인했다. 기존 교육·이미지 보존과 실패 후 파일 재사용 테스트도 통과했다.
- 0004·0005의 실제 SQL과 역방향 SQL을 확인하고 실제 PostgreSQL에서 기존 두 행의 UUIDv7 개별 부여·기존 값 보존·제약 역적용 후 재적용의 UUID 보존을 검증했다. UUID 필드가 없는 historical 모델 INSERT도 DB 기본값으로 보호됨을 확인했다. migration 테스트의 executor를 전환마다 새로 생성하여 stale 상태를 사용하지 않도록 수정했다.
- local dev·loopback DB와 로컬 Storage임을 검사한 뒤 0004 → 0005를 적용했다. 기존 교육 3개의 모든 기존 필드·이미지 키 보존 및 UUIDv7 고유성을 비교했다. 파일 이동·개발 데이터 삭제는 하지 않았다.
- Django 검토 기준으로 UUID 생성 시점·저장 키·프리셋 복구·DB 기본값·migration 정/역방향·문서 정합성을 점검했다. media_id는 편집 입력에서 제외하는 고정 식별자이며 직접 ORM으로 재할당하는 것을 막는 DB trigger는 추가하지 않았다. 실제 AWS 호출·브라우저 재검증·commit·push는 하지 않았다.

## Reset Verification Results

- 2026-10-21: 사용자가 수집 기록 제거·migration 재생성·개발 DB 컨테이너 및 볼륨 삭제를 직접 요청했다. 위 과거 migration 번호·backfill·잠금 제한·기존 DB 보존 결과는 현재 적용 방식이 아니다.
- source_url·source_image_url·collected_on·editorial_note를 모델과 상세에서 제거하고 프리셋 JSON에만 보존했다. 초기화에서 네 키를 제외하며 media_id는 Python default=uuid7만 사용한다.
- 0001은 그대로 유지했다. 0002~0006 파일을 삭제하고 Django makemigrations education --name improve_education_model --noinput으로 0002_improve_education_model을 생성했다. 생성 파일의 import·서식만 Ruff로 정리했고 migration 코드를 직접 작성·수정하지 않았다.
- Compose 구성에서 서비스 db와 볼륨 awesomeschool-assignment_postgres_data를 확인했다. 이 프로젝트의 컨테이너·볼륨·네트워크를 삭제 후 재생성했고 PostgreSQL healthy 상태에서 빈 DB에 migration을 적용했다. 기존 DB 데이터와 계정은 초기화되며 프리셋 원본·로컬 media 파일·실제 .env는 삭제하지 않았다.
- 초기화 첫 실행은 생성 3개·건너뜀 0개, 재실행은 생성 0개·건너뜀 3개였다. 실제 DB의 migration 이력이 0001·0002뿐이고 수집 기록 열이 없음을 introspection으로 확인했다. JSON의 모든 운영 필드·고정 UUIDv7·SHA256 저장 키·이미지 원본 bytes가 DB 및 저장 파일과 일치하고 재실행 후 값이 변하지 않았다.
- 실제 PostgreSQL에서 test education 58개 통과. Django check·migration 변경 누락·Ruff lint/format·CSS 빌드·OpenSpec strict·git diff --check 통과. sqlmigrate로 DROP COLUMN·UUID 고유 열 추가가 생성됨을 확인했다. migration 테스트는 기존 데이터 보존 대신 빈 0001 → 최종 schema → 프리셋 생성을 검증한다.
- 랜딩·상세의 HTTP 200과 출처 영역 제거를 Django client로 확인했다. 실제 브라우저의 화면 너비별 재검증·AWS 연결·관리자 계정 재생성·commit·push는 수행하지 않았다. 이전 migration을 적용한 DB에 대한 업그레이드 호환성과 무중단 적용은 지원하지 않는다.

- 출처 영역 제거 후 CSS를 재생성했다. 첫 재빌드 비교에서 차이가 있어 연속 빌드를 추가 확인했고 최종 연속 빌드의 SHA256이 일치했다: D99607ECA4DB07E8D54ACCE4A724ADDD91E85A6526F66C3209F02E28708356B3.
