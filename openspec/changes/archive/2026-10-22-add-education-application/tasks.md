# Tasks

## 1. Q2와 환경별 실행 기반

- [x] 1.1 django-q2 공통 의존성과 django-ses 운영 의존성을 기존 uv 그룹에 추가하고 lock한다. events extra는 추가하지 않는다. Python 3.14/Django 6.1 조합의 설치·import와 `uv sync --locked` 재현성을 확인한다.
- [x] 1.2 base/dev/prod에 ORM broker·기본 큐·workers=2와 설계의 timeout/retry/대기량·실패 정책을 적용한다. Django 이메일 backend를 dev locmem/prod django-ses로 설정하고 필수 SES 설정·SDK timeout/단일 시도·로그 보호를 `.env.example`과 함께 반영한다. `test_settings.py`에서 dev AWS 접근 없음·prod 누락/충돌·실패 시 fallback 없음·동일 DB alias·이벤트 설정 불필요를 검증한다.
- [x] 1.3 README·architecture·task-queue-comparison에 기본 큐 하나·별도 qcluster 실행·설정 변경 후 정상 재시작·운영 의존성 선택을 동기화한다. 문서 명령·환경 변수와 실제 설정이 일치하는지 확인하고 실제 자원 생성·발송은 수행하지 않는다.

## 2. 신청·안내 기록과 DRF API

- [x] 2.1 Application·ApplicationNotification·MailAttempt·공유 전송 예산 모델과 추가 migration을 Django 명령으로 생성한다. 실제 PostgreSQL 테스트에서 request_id·신청별 안내의 고유성, received 기본값, 안내 pending·시도 0·시도 기록/접수 필드 없음, slug snapshot·교육 삭제 시 신청 보존, 기존 교육·프리셋 보존을 검증하고 `makemigrations --check --dry-run`·`sqlmigrate`를 확인한다. 기존 migration·DB는 초기화하지 않는다.
- [x] 2.2 교육 GET·신청 POST serializer와 API URL을 설계의 JSON 필드·응답 형식으로 구현한다. `test_api.py`에서 education_slug 식별·image_alt를 포함한 공개 필드·중단/없는 교육·필수값·이메일·우편번호·오늘 포함 날짜 경계·문자열 공백/상세주소 정규화·정의 밖 필드 거부·201 최소 응답·오류 형식과 신청/안내의 원자적 저장을 실제 ORM으로 검증한다.
- [x] 2.3 request_id 반복 제출·409 충돌·동시 요청 보호를 구현한다. 실제 별도 DB 연결/transaction 테스트로 최초 생성과 동일 정규화 입력 재요청의 201/200·날짜 경과·교육 중단/slug 변경/삭제 후 재시도·다른 입력 충돌·신청/안내 각각 한 건을 확인한다.
- [x] 2.4 익명 POST의 명시적 CSRF 경계와 최소 응답을 적용한다. CSRF 검사를 강제한 API 테스트로 token 없음 403·정상 token 성공·GET 신청 목록 405·조회/수정/삭제 미제공·개인정보 비노출을 확인하고 README에 GET 해석·API 예제·오류 계약·신청 관리 후속 범위를 기록한다.

## 3. Axios 신청 화면과 주소 검색

- [x] 3.1 Axios 버전·라이선스·로컬 배포 자산 복사 명령을 npm lockfile과 함께 추가한다. 같은 lock으로 재생성한 배포 파일을 비교하고 브라우저에서 외부 Axios CDN 없이 로딩되는지 확인한다. architecture·development의 배포 자산/개발 도구 설명을 갱신한다.
- [x] 3.2 공통 layout을 사용하는 신청 HTML·JavaScript와 접수 가능 교육의 실제 링크를 추가한다. Axios GET 로딩/실패/중단 상태와 POST 진행/필드 오류/일반 오류/접수 완료를 구현하고 기존 `test_pages.py`의 링크 없음 assertion·footer 안내를 갱신해 서버 렌더링·escaping·중단 상태를 검증한다.
- [x] 3.3 Kakao embed 검색·SDK 지연 로딩·주소 자동 입력·직접 입력·검색 취소와 포커스 복구를 구현한다. fake SDK callback으로 결과·취소·로딩 실패·기존 입력 보존을 확인하고 공식 SDK·주소검색에 필요한 네트워크와 직접 입력 대안을 README에 기록한다.
- [x] 3.4 모바일 label·키보드·자동완성·날짜 선택·오류 focus·상태 안내·중복 클릭 차단을 적용하고 Tailwind CSS를 재빌드한다. 브라우저에서 360/390/768/1280px의 넘침·터치 영역과 서버 저장 후 응답 유실을 재현한다. 미확인 시 편집 잠금·원래 payload/ID 재시도·교육 중단 후 기존 접수 확인·확정 오류 후 수정·재시도 중 CSRF 만료 후 ID 유지·409 자동 재전송 없음·새로고침 시 보호 한계 안내를 검증한다. Android Chrome/iOS Safari 실제 검증 여부를 구분해 기록한다.

## 4. 날짜별 검사와 개발 모의 처리

- [x] 4.1 한국 날짜 09시 due_at·당일 늦은 신청·중단 후 catch-up과 due_at/PK 순의 batch당 100건 이하 등록을 구현한다. `test_notifications.py`에서 시간 고정·실제 ORM으로 예약 전 미실행·기존 상태 복구 우선·100건 초과의 다음 batch·20초 실행 예산 후 후속 등록·메일 queued 200건 적체 시 중단·중복 검사·enqueue/후속 등록 실패 rollback·다음 정기 검사 복구를 검증한다.
- [x] 4.2 row lock 기반 처리권·시도 식별자 영속화와 상태 전이 표를 구현한다. PostgreSQL 동시 실행 테스트로 한 시도만 외부 경계를 호출하는지, 최초 queued는 시도 0이고 재시도 queued는 이전 횟수를 유지하며 예산 미확보 시 추가 시도가 없는지 확인한다. stale queued→pending·sending→unknown·현재 attempt_id/예상 상태 일치 갱신·늦은 실패의 완료 상태 덮어쓰기 방지·attempt/notification 결과 원자성을 검증한다.
- [x] 4.3 한국어 HTML·일반 텍스트 안내 template와 공통 EmailMultiAlternatives 전송 경로를 구현한다. 개발은 실제 locmem backend로 검증해 정확한 날짜·지연 문구·escaping·불필요 개인정보 제외·메일 한 건 처리를 확인한다. SDK/credential/SMTP 접근 없이 한 번만 모의 완료되며 sent_at·MessageId가 비어 있는지 검증한다.
- [x] 4.4 주기 스케줄을 고유 이름으로 설정하는 `configure_background_tasks` 명령을 구현한다. 반복 실행·dev/prod 선택 테스트로 안내 스케줄 중복 없음·이벤트 수집 스케줄 없음·catch_up 정책을 확인하고 README에 준비/실행 명령과 모의 처리 조회 방법을 기록한다.

## 5. 운영 SES 발송과 API 결과 기록

- [x] 5.1 공통 Django 이메일 API에서 django-ses로 발송하고 task가 message.send 반환값·같은 message의 MessageId를 확인해 attempt/notification의 접수 결과를 저장한다. backend는 실제로 사용하고 SDK 경계만 Stubber/fake로 대체해 본문·한 건 전송·단일 SDK 호출·반환 1+MessageId의 accepted·확실한 미전송 0의 failed·MessageId 누락/결과 불일치의 unknown을 검증한다. 업무 DB 기록용 signal receiver·SNS 연결은 추가하지 않는다.
- [x] 5.2 미접수 확정 일시 오류·일일 한도·설정 오류·결과 불명을 분류하고 총 3회 제한을 구현한다. 시간 고정 테스트로 일반 5분/15분·일일 한도 실패 후 24시간·오류 종류 변경 시 횟수 유지·검사 전 미실행·응답 유실/발송 후 task DB 기록 실패/미분류 오류의 unknown·자동 재발송 없음·한도 초과 보존을 검증한다. Q2·django-ses 로그의 안전한 오류 코드와 예외 원문·개인정보 비노출을 확인한다.
- [x] 5.3 여러 worker가 공유하는 DB 전송 예산과 대기 처리의 순서를 구현하고 django-ses의 프로세스별 자동 throttle을 끈다. 실제 DB 동시 실행 테스트로 계정별 설정 속도 준수·예산 미확보 시 시도 횟수 미증가·미처리 대상 보존을 확인한다.
- [x] 5.4 응답 유실·worker 종료·결과 저장 실패와 늦게 도착한 동일 시도의 API 성공 응답을 재현한다. DB 장애 시 남은 sending의 unknown 복구·unknown에서 현재 시도 성공 증거로만 accepted 복구·중복/이전 시도의 결과 무시·시간 경과/재전달만으로 재전송 또는 성공/미발송 판정 없음·외부 호출 횟수를 검증한다. SNS/SQS·웹훅·이벤트 parser와 fixture는 추가하지 않는다.
- [x] 5.5 오래된 sending을 unknown으로 보존하고 제한된 운영 조회 명령을 제공한다. 테스트로 확인 필요 건수·attempt ID·안전한 상태 조회와 본문/수신자 비노출을 확인한다. 조회 명령은 발송 상태를 증거 없이 변경하거나 수동 재발송하지 않는다.
- [x] 5.6 README·architecture·task-queue-comparison에 환경별 이메일 backend·SES 발신자·IAM·한도·운영 환경 변수·결과 불명 조치와 개발 무전송을 기록한다. 배치/적체 제어·실제 재시도 시각의 지연·일일 한도의 24시간 대기로 인한 날짜 경과를 설명하고 API 접수와 실제 전달을 구분하며 SNS·웹훅·반송 확인을 후속 범위로 명시한다. 설정 검사와 문서의 필드가 일치하고 AWS 리소스 생성·비용 발생·실발송을 수행하지 않았는지 확인한다.

## 6. 기존 이미지 수명주기의 비동기 전환

- [x] 6.1 Education 일반 save의 transaction 경계와 기존 signals를 수정해 같은 DB의 Q2 ORM 큐에 정리 작업을 등록한다. `test_media.py`에서 단일/일괄 삭제·교체 commit 전 큐 비가시성·rollback 시 작업 없음·enqueue 실패 시 DB 변경 rollback을 검증한다.
- [x] 6.2 Storage/DB alias와 파일 키로 실행하는 이미지 task·제한 재시도를 구현한다. 실제 임시 Storage로 공유·재연결·동일 키·image 제외 수정·없는 파일·중복 실행·안전한 실패 기록·수동 재등록 후 재검사를 검증한다.
- [x] 6.3 기존 media/preset 테스트를 작업 실행 전후로 나누고 프리셋 삭제 후 재생성·이전 경로·UUIDv7 경로·실패 파일 재사용을 검증한다. 관련 모델·signal docstring과 README·architecture의 동기 정리 설명을 갱신하고 전수 청소·원본 삭제·DLQ가 추가되지 않았는지 확인한다.

## 7. 통합 검증과 완료 증거

- [x] 7.1 임시 PostgreSQL 테스트 DB·임시 미디어에서 실제 qcluster subprocess로 신청→모의 메일·이미지 정리·실패 재등록 흐름을 검증한다. 실제 DB·상태 전이를 mock하지 않고 queued/sending 중단 후 복구와 안전한 정상 종료·결과 flush를 관찰하며 Linux/Windows 미검증 범위를 구분해 기록한다.
- [x] 7.2 서버와 실제 브라우저에서 교육 GET→주소 입력→신청 POST→접수 표시를 검증한다. 로컬 Axios/CSS HTTP 200·주소 SDK 실패 대안·키보드 탐색·반응형을 확인하고 모바일 실제 기기 검증을 desktop 크기 조절 결과와 구분한다.
- [x] 7.3 `uv run python src/manage.py check`, `makemigrations --check --dry-run`, `test education`, `uv run ruff check .`, `uv run ruff format --check .`, `npm run build:css`, `git diff --check`, `openspec validate add-education-application --strict`를 수행한다. 실패 원인을 regression/환경/명령 오류로 구분하고 수정 영향 범위만 재검증한다.
- [x] 7.4 CSRF·개인정보·동시 발송 claim·결과 불명·작업 등록 transaction의 diff와 검증 증거를 독립 관점에서 검토한다. blocking defect를 해결한 뒤 README 구현 상태·실행/검증 결과·잔여 운영 준비·AI 도구 내역을 최종 일치시키고 미실행 AWS/실기기 검증을 성공으로 표시하지 않는다.

## 8. 상담 안내 이메일 task 명칭과 내부 처리 정리

아래 항목은 기존 1~7절 구현·검증 이후 추가된 구조 정리 작업이다. 기존 완료 표시는 이전 구현의 검증 기록이며 이번 정리의 완료는 아래 항목의 검증 결과로 별도 추적한다.

- [x] 8.1 Q2 진입점을 `enqueue_consultation_reminder_emails`·`send_consultation_reminder_email`·`delete_unreferenced_education_image`로 변경한다. 모든 async_task·후속 검사·signals·스케줄 준비 명령의 dotted path와 테스트 참조를 함께 바꾸고, 실제 ORM 큐 payload가 새 경로와 기존 인자·ACK 정책을 유지하는지 확인한다.
- [x] 8.2 `tasks.py`에는 실제 task 함수와 실행 흐름을 두고 긴 내부 처리만 `tasks_support/consultation_reminder_dispatch.py`·`consultation_reminder_delivery.py`로 분리한다. 기존 `notifications.py`의 메일 생성·오류/결과 분류를 delivery에 통합하고 공유 예외는 `tasks_support/exceptions.py`에 둔다. 짧은 이미지 정리는 task 안에 유지하고 `_eligible`은 사용 위치에 인라인하며 단순 위임 함수·역방향 import·범용 util 계층을 추가하지 않는다. 두 대상 조회 조건의 일치와 모델·schema·함수 인자·반환 계약 보존을 확인한다.
- [x] 8.3 기존 스케줄 이름·row·next_run을 유지한 함수 경로 전환을 구현·검증한다. 기존 함수 경로의 Schedule fixture에서 준비 명령을 반복 실행해 동일 PK·다음 시각·스케줄 한 건·새 func와 기존 주기/반복/cluster 정책을 확인한다. 기존 경로의 대기·실행 작업 확인과 기존 worker로 정상 처리 후 전환하는 절차, 과거 이미지 실패를 새 경로·기존 인자로 재등록하는 방법을 문서화한다. 큐 payload 직접 편집·이력 삭제·메일 강제 재발송은 하지 않는다.
- [x] 8.4 이동한 구현에 맞춰 테스트 import·patch를 수정하고 PostgreSQL 동시 claim·공유 예산·날짜/재시도 조건·등록 rollback·늦은 결과·unknown 보존·이미지 재검사를 유지한다. 실제 qcluster subprocess에서 새 함수 경로의 메일·이미지·후속 검사 실행과 정상 종료·강제 종료 복구·실패 재등록을 검증한다. DB·내부 상태 전이를 mock하거나 기존 보장 검사를 제거하지 않는다.
- [x] 8.5 README·architecture·관련 운영 설명과 docstring을 새 명칭·지원 모듈의 역할에 맞춘다. Django check·makemigrations --check --dry-run·전체 test education·Ruff lint/format·git diff --check·OpenSpec strict validate를 실행하고 구조 정리로 schema 변경이 생기지 않았는지 확인한다. 화면·자산 변경이 없으면 CSS 빌드·브라우저 검증은 반복하지 않으며 AWS 실발송·운영 데이터 변경은 수행하지 않는다.

## Workflow follow-up

- 구현·검증·검토가 끝난 뒤 사용자 요청에 따라 메인 명세 동기화·archive를 진행한다. 이 계획 작성만으로 구현·commit·push·배포를 시작하지 않는다.
