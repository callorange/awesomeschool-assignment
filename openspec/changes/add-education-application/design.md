# Design

## Context

동기는 [proposal.md](proposal.md)를 따른다. 현재 `src/education/`에는 Education·공개 페이지·프리셋 명령이 있고 신청 모델·serializer·API·JavaScript는 없다. DRF는 등록됐지만 API endpoint는 없으며 frontend는 Tailwind CLI만 사용한다. 공통 template는 `src/templates/base.html`, 자산은 `src/static/`에 통합되어 있다.

`signals.py`는 pre_save에서 이전 이미지 키를 읽고 post_save/post_delete에서 `on_commit` callback으로 참조를 재검사해 직접 삭제한다. `test_media.py`는 실제 PostgreSQL transaction과 임시 Storage로 즉시 삭제·rollback·공유·재연결·프리셋 재생성을 검사한다. 비동기 전환 시 즉시 삭제 assertion을 작업 실행 후 검사로 바꾸되 보존 계약은 유지해야 한다.

설정은 base/dev/prod로 분리되고 dev는 AWS를 사용하지 않는다. prod의 django-storages S3 의존성은 이미 boto3를 포함한다. base의 console 메일 설정은 새 모의 처리 완료 기록을 대신하지 못한다. 기존 문서의 fetch 예정·자동 메일 미정·신청 목록 API 예정 설명은 이번 승인 범위와 달라 구현 시 동기화한다.

## Goals / Non-Goals

**Goals:**

- [신청 명세](specs/education-applications/spec.md), [안내 명세](specs/application-notifications/spec.md), [작업 명세](specs/background-processing/spec.md), [교육 delta](specs/education-catalog/spec.md)를 기존 단일 앱에서 충족한다.
- DB 일관성과 외부 발송의 불확실성을 구분한다. 기록·처리권·증거로 중복과 누락을 관리하고, 실패를 성공으로 숨기지 않는다.
- 일반적인 단일 기본 큐로 시작하며 메일 1건과 이미지 1개가 각각 제한된 실행 시간을 갖게 한다.

**Non-Goals:**

- 외부 메일의 exactly-once 전달 보장, 임의의 작업을 위한 범용 workflow/outbox framework, 모든 저장소 파일 전수 청소.
- 신청 관리 UI/API나 메일 수동 재발송 웹 화면. 결과 확인은 제한된 운영 명령·기록 조회로 제공한다.
- 계획 단계에서 패키지 설치, migration 실행, AWS 리소스 생성·과금 호출. 운영 준비 계약만 정의한다.

## Decisions

### 1. 같은 앱의 모델과 명시적 공개 API

`education/models.py`에 Application과 ApplicationNotification을 추가한다. 단순 CRUD를 위해 Service·Repository 앱을 만들지 않는다. API는 `education/api.py`, serializer는 `education/serializers.py`, 작업은 `education/tasks.py`, SES 연계는 `education/notifications.py`에서 담당한다. 같은 책임이 비대해지지 않는 한 파일을 더 잘게 나누지 않는다.

Application은 교육 FK, 신청 당시 교육 slug·교육명 snapshot, 이름(100자)·이메일(254자)·우편번호(5자리 문자열)·기본주소(255자)·상세주소(255자, 선택)·연락 가능 날짜, 고유한 request_id(UUID), 서버 기본 상태 `received`/표시 `접수`, 생성 시각을 보관한다. 문자열 입력은 바깥 공백만 제거하고 이메일 대소문자·주소 내용을 자의적으로 변경하지 않는다. 상세주소 생략은 빈 문자열로 정규화하고 UUID·날짜는 파싱한 값으로 비교한다. 연락 가능 날짜는 `timezone.localdate()` 기준 오늘을 포함해 허용한다. 전화번호·일정 확정·주소 진위 인증은 추가하지 않는다.

교육 삭제로 신청·안내가 연쇄 삭제되지 않도록 FK는 nullable SET_NULL로 두고 신청 당시 snapshot을 유지한다. snapshot은 접수 이후의 콘텐츠 수정과 무관한 안내 근거다. 향후 상태 변경 값은 이번 기능에 노출하지 않는다.

| 경로 | 구현·역할 |
| --- | --- |
| `/educations/<slug>/apply/` | 기존 render 방식의 HTML shell·CSRF token·선택 slug 제공 |
| `GET /api/educations/<slug>/` | DRF RetrieveAPIView·교육 안내 serializer. 접수 중단도 공개 |
| `POST /api/applications/` | DRF CreateAPIView·명시적 입력 serializer와 성공 응답. GET은 405 |

교육 GET의 필드는 `slug`, `title`, `summary`, `image_url`, `image_alt`, `operation_type`, `operation_note`, `is_accepting_inquiries`다. 신청 POST는 다음 JSON 필드만 받는다. `contact_date`는 `YYYY-MM-DD`, `request_id`는 UUID 문자열이며 아래 값은 문서용 예시다.

```json
{
  "education_slug": "prompt",
  "name": "홍길동",
  "email": "applicant@example.com",
  "postal_code": "04524",
  "address": "서울특별시 중구 세종대로 110",
  "address_detail": "",
  "contact_date": "2026-10-22",
  "request_id": "c8ce39db-7e31-4f91-9dbb-a761f38ea98e"
}
```

최초 201·동일 제출 재사용 200의 응답은 `{"request_id":"c8ce39db-7e31-4f91-9dbb-a761f38ea98e","status":"received","status_display":"접수"}`로 동일하다. 내부 PK나 개인정보는 반환하지 않는다. 400은 DRF의 필드별 문자열 배열과 `non_field_errors`를 사용하고, 404·409·일반 오류는 `detail`로 안내한다. 409에서 클라이언트가 새 ID를 자동 생성하지 않는다. framework의 HTML CSRF 오류는 아래 일반 실패 규칙으로 처리한다.

공개 신청 목록 GET을 추가하는 대신 교육정보 GET을 사용한다. 과제 원문은 GET 대상이 명확하지 않으므로 README에 이번 해석과 신청 관리의 후속 범위를 명시한다. 개인정보 조회·상태 변경을 추가해 요구를 넓히지 않는다.

POST serializer는 알 수 없는 상태 입력을 포함해 정의하지 않은 쓰기 필드를 거부한다. 최신 접수 상태는 저장 transaction 안에서 교육 row lock으로 읽어 중단·삭제와 경쟁하는 요청의 판정 시점을 고정한다. 접수 후 교육 중단은 기존 안내를 취소하지 않는다.

### 2. 반복 제출과 개인정보 경계

브라우저가 제출 시 request_id와 전송 payload의 메모리 snapshot을 만들고 결과 확인 전의 재시도에는 둘을 그대로 사용한다. 전체 새로고침을 넘어 개인정보를 localStorage에 보존하지 않는다. 동일 정규화 입력·request_id이면 기존의 최소 접수 결과를 200으로 반환한다. 첫 생성은 201, 다른 입력으로 식별자를 재사용하면 409다. 이메일만으로 여러 교육·상담 신청을 합치지 않는다.

DB unique 제약과 transaction/savepoint로 동시 POST를 처리한다. 1절의 형식·정규화 검사 후 기존 request_id를 확인하고 저장 당시 slug snapshot과 정규화 입력을 비교한다. 기존 제출 확인은 새 신청의 날짜·최신 교육 검증보다 먼저 하여 접수 후 날짜가 지났거나 교육이 중단·변경·삭제돼도 동일 제출의 성공을 확인한다. 기존 결과 응답은 request_id·`received`·`접수`뿐이다. 비교를 위해 기존 개인정보를 응답하거나 로그로 남기지 않는다.

최초 제출 중에는 편집·재클릭을 막는다. 통신 실패·timeout·5xx·해석 불가능한 응답은 저장 여부 미확인으로 안내하고 입력을 읽기 전용으로 유지하며 원래 payload를 재시도하는 버튼만 제공한다. 201/200이면 접수 완료, 저장되지 않았음이 확정된 API 400/404 또는 최초 요청의 CSRF 403이면 편집을 허용하고 다음 제출에서 새 ID를 만든다. 이전부터 결과가 미확인인 요청의 재시도에서 403이 발생하면 이전 저장 여부는 여전히 미확인이므로 snapshot을 유지하고 CSRF token 갱신 후 같은 요청을 재시도한다. 409는 충돌 안내 후 자동 재제출을 중단하고 ID·snapshot을 보존한다. 미확인 상태에서 새 ID나 변경 payload를 자동 전송하지 않는다. 새로고침·탭 종료까지 snapshot을 복구하는 기능은 이번 범위에 없으며 그 경우 반복 제출 보호가 이어지지 않는 한계를 명시한다.

익명 POST도 `csrf_protect` 경계에서 검사하고 template의 token을 Axios의 `X-CSRFToken`으로 전달한다. DRF SessionAuthentication만으로 익명 CSRF가 보장된다고 가정하지 않는다. 같은 origin으로 제공하므로 JWT·CORS 패키지는 추가하지 않는다. framework CSRF 오류가 HTML이어도 프론트가 일반 실패로 처리해야 한다.

### 3. Axios와 주소 검색을 사용하는 반응형 폼

기존 template layout을 확장하고 `src/templates/education/application.html`, `src/static/js/application.js`에 폼·화면 처리를 둔다. Axios의 고정 npm 버전을 lockfile로 관리하고 브라우저 배포 파일·라이선스를 `src/static/vendor/axios/`에 재현 가능한 복사 명령으로 포함한다. 평가자는 npm이나 외부 Axios CDN 없이 실행한다. 새 bundler·SPA는 추가하지 않는다. 현재 npm의 dev-only 설명은 빌드 도구와 배포 자산 의존성을 구분하도록 갱신한다.

신청 화면은 Axios GET 결과로 교육명·소개·이미지·운영 안내·접수 상태를 표시한다. 조회 전·조회 실패·중단 상태에서는 신규 제출을 막는다. 결과 미확인인 기존 제출은 교육이 이후 중단돼도 2절의 원래 payload 재시도로 확인할 수 있다. 네트워크 중복 전송을 자동 retry하는 interceptor는 만들지 않는다.

주소 검색은 [Kakao 공식 SDK](https://postcode.map.kakao.com/guide)의 HTTPS `t1.kakaocdn.net`·`kakao.Postcode`·`embed()`를 사용한다. 검색 버튼을 누를 때 SDK를 로딩하고 폼 내부의 폭 100% 영역에 검색을 삽입한다. 검색/취소 시 값·포커스를 보존한다. 선택한 우편번호·기본주소를 입력하고 상세주소로 이동한다. 주소 필드를 직접 수정할 수 있게 하여 외부 장애가 필수 신청 경로를 막지 않게 한다. 로고를 가리거나 SDK를 수정·자체 복제하지 않는다. 주소 검색에 필요한 검색어만 외부 서비스에 입력하고 신청자명·이메일·상세주소를 검색 요청에 붙이지 않는다.

모바일 1열·넓은 화면의 제한된 폼 폭, 16px 이상 입력 글자·44px 이상 터치 영역, label·autocomplete·native date input·aria-live 안내·오류 focus를 사용한다. 360·390·768·1280px에서 잘림·가로 스크롤·키보드·검색 높이를 확인한다. Android Chrome·iOS Safari 실제 테스트가 불가능하면 responsive desktop 검증과 구분해 미검증으로 남긴다.

### 4. 단일 큐의 등록·실행과 주기 작업

`django-q2` 1.11 계열을 공통 의존성에 추가하고 Python 3.14/Django 6.1 호환 조합을 lock한다. `Q_CLUSTER`의 ORM broker는 현재 유일한 DB alias `default`, 대체 cluster 없이 큐도 기본 `default`를 사용한다. 개발 명령은 `uv run python src/manage.py qcluster`, 운영은 prod 설정을 주입하고 `uv run --no-sync python src/manage.py qcluster`로 실행한다.

초기값은 workers=2, bulk=1, queue_limit=2, timeout=60초, retry=300초, max_attempts=3, ack_failures=True, catch_up=False다. worker 수 자동 증감·독립 cluster 추가는 하지 않는다. 이미지 작업만 `ack_failure=False`로 등록한다. 메일과 주기 작업은 정상 실패의 재등록을 발송 기록·다음 검사에 맡기고 안전한 예외만 Q2 실패 목록에 남긴다. 요청 수신부터 결과 기록까지 retry보다 짧게 끝나도록 batch·외부 통신 시간을 제한하고 실제 worker로 검증한다.

고유 이름의 관리 명령 `configure_background_tasks`로 5분 간격 안내 대상 검사 스케줄을 중복 없이 설정한다. SES 이벤트 수집 스케줄은 만들지 않는다. management command가 명시적으로 만드는 스케줄이며 AppConfig.ready·import·migration에서 외부 연결이나 중복 스케줄 생성을 하지 않는다. 시작 전 준비 명령과 단일 scheduler 운용을 README에 기록한다.

검사는 먼저 10분 이상 남은 queued를 pending으로, 결과 없는 sending을 unknown으로 복구한 뒤 발송 대상을 선택한다. 복구도 batch 단위의 짧은 row lock과 조건부 갱신을 사용한다. pending 또는 next_retry_at이 지난 retry_wait 중 due_at이 지난 대상만 `due_at → PK` 순으로 batch당 최대 100개 선택한다. notification row를 짧게 잠그고 같은 transaction에서 ORM 큐에 건별 작업을 등록하고 queued·queued_at을 기록한다. enqueue가 실패하면 해당 기록도 rollback된다. 중복 검사에는 skip_locked를 사용한다. 뒤늦게 도착한 중복 큐 작업도 처리권 확보 단계에서 걸러진다.

100건은 한 검사 주기의 총량 제한이 아니다. 실행당 복구·등록에 최대 20초를 사용하며, 여유가 있으면 같은 실행에서 다음 batch를 이어 처리한다. queued 메일이 200건 이상이면 추가 등록을 멈추고, 그 미만이면 관측한 여유만큼만 등록한다. 이는 DB 큐 적체를 제한하기 위한 기준이며 Q2의 프로세스 내부 queue_limit=2와 구분한다. 처리 예산을 소진했지만 대상과 등록 여유가 남으면 같은 기본 큐에 후속 검사 한 건을 등록한다. 여유가 없으면 즉시 검사를 반복하지 않고 다음 5분 검사에서 재개한다. 후속 등록도 DB transaction과 함께 수행하며 실패·중단 시 정기 검사가 영속 대상에서 복구한다. 여러 검사로 대상이 겹쳐도 동일 안내를 중복 발송하지 않는다.

### 5. 메일 기록과 시도 상태 전이

ApplicationNotification은 신청별 OneToOne이며 due_at, mode(simulated/ses), state, queued_at, next_retry_at, 총 시도 횟수, 현재 attempt_id, started_at, simulated_at, sent_at, ses_message_id와 오류 코드를 보관한다. sent_at은 SES API 접수 시각이며 실제 전달 시각이 아니다. 메일 종류는 하나이므로 범용 notification type framework는 만들지 않는다. MailAttempt는 실제 외부 전송 시도별 UUID·notification FK·시작/완료 시각·접수 결과·MessageId·오류 코드만 보관한다. 재시도 이력을 추적하도록 이전 시도를 덮어쓰지 않는다. 전달·반송 상태 필드는 이번에 추가하지 않는다.

신청 직후 기본값은 state=pending·시도 횟수=0이며 queued_at·next_retry_at·현재 attempt_id·started_at·simulated_at·sent_at·ses_message_id는 비어 있다. MailAttempt도 아직 없다. queued는 이번 큐 등록에 대한 발송 시도를 아직 시작하지 않은 상태다. 최초 등록은 시도 0이고 재시도 등록은 이전 횟수·이력을 유지한다. MailAttempt 생성·시도 횟수 증가는 worker가 전송 예산을 확보하고 sending 처리권을 영속화할 때만 수행한다.

```text
pending --> queued --> sending --> accepted
                         |    +--> simulated
                         +-------> retry_wait --> queued
                         +-------> failed
                         +-------> unknown
```

신청 저장과 notification 생성은 같은 transaction이다. due_at은 연락 가능 날짜의 Asia/Seoul 09시와 생성 시각 중 늦은 값으로 정하고 UTC로 저장한다. 중단 기간에 날짜가 지났어도 누락시키지 않고 catch-up한다. 발송 대상을 지우거나 신청 상태를 완료로 바꾸지 않는다. 오늘 포함·09시·5분 정기 검사·지연 복구를 기본 정책으로 사용한다. retry_wait의 next_retry_at은 재시도 가능한 최초 시각이며 검사·큐 지연으로 실제 발송은 늦어질 수 있다.

worker는 notification row lock으로 허용 상태·due_at·시도 한도를 확인하고 MailAttempt와 sending을 commit한 뒤 외부 호출한다. 긴 네트워크 호출 중 DB transaction을 열어두지 않는다. sending/accepted/simulated/unknown인 중복 작업은 보내지 않는다. 10분 이상 결과 없는 sending은 unknown으로 분류하며 TTL 만료만으로 새 메일을 보내지 않는다. 아직 실행 중인 동일 시도의 성공 응답이 뒤늦게 기록되는 경우에는 해당 증거를 반영할 수 있지만 새 발송은 시작하지 않는다.

| 원래 상태・조건 | 다음 상태・원자적 처리 |
| --- | --- |
| 신청 생성 | pending, 시도 횟수 0, MailAttempt 없음 |
| pending 또는 기한이 된 retry_wait | queued와 같은 transaction의 큐 등록 |
| queued, 전송 예산 미확보 | retry_wait·다음 허용 시각, 새 MailAttempt·시도 증가 없음 |
| queued, due_at·next_retry_at 경과·예산 확보 | sending·새 attempt_id·MailAttempt 생성·시도 증가 |
| 10분 이상 queued, 아직 sending 아님 | pending, 시도 이력은 유지하고 다시 등록 가능 |
| sending, 6절의 확정 결과 | 같은 attempt_id에만 accepted/simulated/retry_wait/failed 반영 |
| 10분 이상 결과 없는 sending | unknown, 재전송하지 않음 |
| unknown, 같은 현재 시도의 뒤늦은 성공 응답과 MessageId | accepted, 새로운 외부 호출 없음 |
| accepted 또는 simulated | 어떤 중복·늦은 실패 처리도 상태를 바꾸지 않음 |

각 결과는 MailAttempt와 notification을 같은 짧은 transaction에서 갱신한다. 실패·복구 갱신은 예상 state와 attempt_id를 조건으로 하여 성공 기록을 덮어쓰지 않는다. DB 장애로 unknown조차 저장할 수 없으면 sending을 남겨 정기 검사에서 unknown으로 복구한다. 허용된 queued 상태가 아닌 중복 큐 작업이거나 due_at·next_retry_at 전이면 보내지 않는다. 개발의 simulated도 동일한 처리권·완료 불변조건을 사용한다.

개발과 운영은 같은 `EmailMultiAlternatives` 생성·전송 경로를 사용하고 Django 이메일 backend 설정으로 분기한다. Django 6.1의 `MAILERS` 기본 backend는 dev에서 `django.core.mail.backends.locmem.EmailBackend`, prod에서 `django_ses.SESBackend`로 지정한다. 개발은 locmem이 한 건을 처리한 뒤 simulated_at만 기록하며 sent_at·SES MessageId를 만들지 않는다. SES client 생성·credential 조회·SMTP 연결·본문 console 출력은 하지 않는다. locmem outbox는 개발 프로세스 메모리에만 존재하고 영속 처리 여부는 notification 기록으로 확인한다. 운영으로 설정만 바꿔 개발의 simulated 데이터를 자동 재발송하지 않으며 dev/prod DB는 분리한다.

최종 본문은 다음 내용을 한국어 HTML/텍스트로 제공한다. template 변수는 escape하며 제목에는 줄바꿈 입력이 들어가지 않게 검증한다.

> 제목: [히어로스쿨] {{ 교육명 }} 상담 신청 안내
>
> 안녕하세요, {{ 신청자명 }}님.
> 히어로스쿨의 {{ 교육명 }} 교육에 관심을 갖고 신청해 주셔서 감사합니다.
> 신청 시 선택하신 연락 가능 날짜는 {{ 연락가능날짜 }}입니다.
> 담당자가 신청 내용을 확인하고 상담 절차를 안내합니다.
> 이번 신청은 상담 접수이며, 교육 일정과 진행 조건은 상담 후 협의하여 확정됩니다.
> 감사합니다. 히어로스쿨 드림

### 6. SES 발송·재시도·전송 속도

운영은 `django-ses`를 prod 그룹에 추가하고 Django 이메일 API로 발송한다. events extra·별도 backend subclass·직접 SES 발송 구현은 추가하지 않는다. task가 `message.send(fail_silently=False)`를 호출하고 반환 건수와 같은 message의 `extra_headers.get('message_id')`를 확인해 현재 attempt와 notification을 함께 저장한다. 업무 DB 기록을 위한 message_sent signal receiver는 만들지 않는다. backend가 message에 기록하는 MessageId 계약은 잠근 릴리스의 실제 backend·fake SDK 통합 테스트로 확인한다.

`USE_SES_V2=True`와 `AWS_SES_CONFIG`의 botocore Config로 `total_max_attempts=1`을 지정해 SDK 자동 네트워크 재시도를 끈다. connect timeout=5초·read timeout=15초로 한정하고 Q2 task timeout보다 먼저 반환되게 한다. 애플리케이션이 판단하지 못한 상태에서 SDK가 재전송하지 않게 하기 위함이다. attempt_id는 로컬 발송 기록과 message 처리 문맥으로 연결한다. 이번에는 이벤트용 tag·configuration set을 요구하지 않는다. SES 접수 후 task의 DB 기록이 실패한 경우도 미접수 오류로 재분류하지 않고 unknown으로 보존한다.

| 결과 | 기록·다음 동작 |
| --- | --- |
| 반환 1이며 MessageId 존재 | attempt/notification의 sent_at·MessageId 기록, accepted |
| 반환 0이며 외부 미전송이 확실 | failed·backend_not_sent, 성공·무조건 재시도로 처리하지 않음 |
| 반환 1이지만 MessageId 없음, 또는 반환과 접수 증거가 불일치 | unknown·invalid_send_result, 자동 재발송하지 않음 |
| 미접수가 확정된 초당 제한 오류 | retry_wait, 첫 실패 후 5분·두 번째 실패 후 15분 |
| 미접수가 확정된 일일 한도 초과 | retry_wait, 각 실패 시점에서 24시간 후 |
| 요청 전 연결 불가가 확실한 오류 | 일반 일시 오류와 같은 5분·15분 정책 |
| 인증·발신자·유효성 오류 | failed, 자동 재시도하지 않음 |
| read timeout·연결 단절·불명확한 5xx·worker 종료·접수 후 결과 저장 실패 | unknown, 자동 재전송하지 않음 |

메일당 총 시도는 최초 포함 3회다. 오류 종류가 달라져도 횟수를 초기화하지 않고 세 번째 실패는 failed로 보존한다. 일일 한도 초과의 24시간은 이 프로젝트의 보수적인 대기 정책이며 SES가 고정 시각에 한도를 초기화한다는 뜻이 아니다. 초당/일일 제한은 SES가 제공하는 오류 코드와 공식 사유를 함께 분류하고 일치하지 않는 오류는 unknown으로 보존한다. SDK 호출 전·후 단계와 알려진 오류를 근거로 미전송을 판단하며 반환 0이나 예외 이름만으로 안전한 재시도를 추측하지 않는다. 개발 locmem 반환 1은 MessageId 없이 simulated이며 운영의 MessageId 필수 규칙과 구분한다.

사용자 정보·예외 원문을 Q2 Failure에 그대로 담지 않는다. 구조화된 안전한 오류 코드를 DB에 기록하고 task가 실패해야 할 때는 attempt ID와 안전한 코드만 포함한 예외를 발생시킨다. Q2 실패 목록을 자동 재전송의 단일 원본으로 쓰지 않는다.

두 worker가 초당 한도를 각각 별도로 적용하지 않도록, 운영 전송 예산의 다음 허용 시각을 DB singleton row에 두고 짧은 row lock으로 공유한다. 예산 확보 전에 MailAttempt·sending을 만들지 않는다. 허용 시점까지 최대 5초만 대기하며 DB lock은 대기 전에 해제하고 재확인한다. 더 긴 대기는 next_retry_at으로 넘겨 5분 주기 때문에 매번 한 건만 발송되는 병목과 worker의 장기 점유를 함께 피한다. SES_MAX_SEND_RATE 환경값은 운영 계정 한도 이하로 준비하고 실제 계정에서 사용하는 다른 발신자 여유도 반영한다. 프로세스별인 django-ses 자체 throttle은 `AWS_SES_AUTO_THROTTLE=None`으로 끄고 이 공유 예산으로 통일한다. 일일 한도 거부도 대상 삭제로 처리하지 않는다. 고정 worker 수만으로 rate limit을 대체하지 않는다.

### 7. API 접수 결과의 범위와 결과 불명 보존

이번 운영 경로는 Django 이메일 API → django-ses → SES API로 끝난다. 성공 응답과 MessageId는 SES가 요청을 접수했다는 증거로만 사용한다. 실제 수신함 도착·수신자 서버 전달·반송·불만 결과는 확인하지 않으며 접수 성공을 실제 전달 성공으로 표시하지 않는다.

prod 필수 설정은 `AWS_SES_REGION_NAME`, `DEFAULT_FROM_EMAIL`, `SES_MAX_SEND_RATE`와 위 backend·SDK 설정이다. 코드에 키를 넣지 않고 IAM role 등 기본 credential chain을 사용한다. SES verified identity·발송 권한·계정 한도는 운영자가 사전에 준비한다. SNS topic·SQS·웹훅 URL·이벤트용 configuration set·서명 검증 설정은 이번 change에 추가하지 않는다.

API 응답이 유실되거나 접수 후 DB 기록에 실패하면 이번 범위에서는 접수 여부를 자동 대조할 수 없다. unknown을 조회 가능한 상태로 보존하고 시간 경과·Q2 작업 재전달·관리 명령 재실행으로 성공 또는 미발송으로 간주하지 않는다. 제한된 운영 명령은 attempt ID·안전한 상태·확인 필요 건수만 조회하며 개인정보 목록·증거 없는 수동 성공 판정·수동 재발송 기능은 제공하지 않는다. django-ses를 포함한 로그에서 수신자·본문·credential·예외 원문을 노출하지 않도록 설정과 테스트를 적용한다.

추가적인 접수 결과 대조·실제 전달·반송 확인이 필요해지면 별도 change에서 SES configuration set → SNS → django-ses HTTPS 웹훅과 이벤트 대조를 추가한다. 그때 출처·서명 검증, 시도와 이벤트의 상관관계, 중복·순서 역전, 수신 DB 오류 시 재전달 정책을 함께 설계한다. 미래 기능을 위한 endpoint·parser·signal receiver·이벤트 fixture·의존성은 미리 만들지 않는다.

근거: [django-ses backend·MessageId·선택적 SNS 연동](https://pypi.org/project/django-ses/), [SDK 재시도](https://docs.aws.amazon.com/boto3/latest/guide/retries.html), [SES 초당·일일 한도 오류](https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas-errors.html). 재시도 5분·15분·24시간은 AWS의 보장값이 아닌 이 프로젝트의 정책이다.

### 8. 이미지 변경과 큐 기록을 같은 transaction으로 저장

이미지 작업은 삭제 후보 키·Storage alias(`default`)·DB alias만 받는다. Storage 객체나 삭제될 교육 instance를 직렬화하지 않는다. worker가 동일 dev/prod 설정의 Storage를 다시 선택하며 로컬 worker는 웹과 같은 MEDIA_ROOT를 사용한다.

현재 on_commit에서 enqueue만 호출하는 안은 commit과 enqueue 사이의 중단을 복구하지 못하므로 채택하지 않는다. [Q2 ORM broker](https://github.com/django-q2/django-q2/blob/v1.11.1/django_q/brokers/orm.py)가 같은 DB alias의 ORM insert를 사용하는 것을 이용해 signals에서 작업을 등록한다. 교육의 일반 save 경계를 `transaction.atomic(using=...)`으로 감싸 post_save까지 포함한다. 단일·QuerySet delete는 Django deletion transaction 안의 post_delete에서 등록한다. 큐 insert 실패 시 교육 DB 변경도 rollback하고 저장소에 새 파일이 남을 수 있는 기존 한계는 유지한다. 새 영속 CleanupJob/outbox 모델은 필요하지 않다.

같은 DB transaction의 미commit 큐 row는 다른 worker에 보이지 않고 rollback 시 사라진다. raw fixture·같은 키·image 제외 update_fields·bulk update 우회 계약은 유지한다. 현재 앱 DB와 Q2 ORM alias가 같음을 설정 검사·테스트로 고정하고 다중 DB broker로의 일반화는 하지 않는다.

작업은 실행 시 Education의 동일 키 참조를 재검사하고 미참조 파일만 Storage.delete한다. 없는 파일은 성공으로 처리하고 나머지 저장소 오류는 안전한 예외로 Q2의 제한적 재시도를 사용한다. 재실행마다 참조를 확인한다. 고정 UUIDv7 경로·프리셋 원본·실패 파일 재사용은 바꾸지 않는다. bulk_update·직접 SQL의 signal 우회는 지원 범위를 넓히지 않고 계속 문서화한다.

### 9. 현재 계약과 테스트·문서의 동기화

기존 페이지 테스트의 신청 링크 없음 assertion은 접수 가능/중단 분기로 바꾼다. base footer의 실제 신청은 원문 사이트 안내는 과제용 상담 접수 기능과 모순되지 않도록 조정한다. `test_media.py`의 commit 직후 파일 부재 assertion은 commit 후 큐 row 존재·worker 실행 뒤 파일 부재로 분리한다. 실제 DB·transaction·Storage·상태 전이는 mock하지 않으며 django-ses의 외부 SES SDK 경계만 fake한다. 개발은 실제 locmem backend로 검증한다.

Q2 설치 후 기존 관리자 앱의 콘텐츠 수 등 테스트 가정을 확인한다. 임시 DB·미디어의 실제 qcluster subprocess에서 작업 처리·실패 재등록·정상 종료를 검증하고 기존 queue/schedule을 건드리지 않는다. Linux의 종료 보장과 Windows 차이를 보고하며 강제 종료를 graceful shutdown 성공으로 기록하지 않는다. 보안 경계 변경에 대한 독립 검토는 apply 완료 시 diff·CSRF·개인정보 테스트·발송 상태 증거로 수행한다. 별도 subagent 사용은 요구하지 않는다.

공통 설정·모델·템플릿 변경을 포함하므로 README의 Django check·migration 누락·education tests·Ruff를 수행하고 CSS를 재빌드한다. API·Q2·메일·이미지 동작을 좁게 검사한 뒤 전체 검사로 확장한다. 실제 AWS와 실제 수신은 별도 opt-in이며 기본 테스트의 필수 조건이 아니다. 기본 주소 검색 계약은 fake callback으로 검사하고 공식 서비스와 모바일 기기의 수동 연결 검증은 별도로 기록한다.

## Risks / Trade-offs

- [SES 외부 발송의 원자성 부재] → 고유 대상·원자적 claim·시도 기록으로 중복을 제어하되 exactly-once 수신을 보장하지 않는다. 응답 유실 시 중복 방지를 우선해 unknown을 자동 재발송하지 않으므로 실제 미발송일 가능성을 자동 해소할 수 없다. 미처리 대상을 보존하는 누락 방지와 실제 수신 보장은 구분한다.
- [접수 이후 결과 미확인] → SES API 접수 성공만 기록하며 실제 전달·반송은 알 수 없다. 추가 확인이 필요해질 때 SNS·웹훅을 후속 도입한다. 이번 운영 준비는 SES 발신자·IAM·계정 한도에 한정하며 앱이 AWS 자원을 자동 생성하지 않는다.
- [하나의 큐에서 메일·이미지·검사 작업 경합] → 2 worker·작은 batch·짧은 I/O·낮은 내부 대기량으로 시작한다. 실제 지연 증거가 생길 때만 cluster 분리를 재검토한다.
- [Q2 at-least-once와 강제 종료] → 재전달 대기 시간·메모리 대기량을 함께 제한하고 메일 claim·이미지 참조 재검사로 안전성을 검증한다. 정상 종료는 내부 대기 작업과 결과 flush 시간을 포함해 기다린다.
- [큐 등록 실패가 이미지 DB 변경까지 실패시킴] → 파일 정리 키를 잃는 성공보다 명시적인 rollback을 선택한다. commit 후 저장소 삭제 실패는 기존처럼 DB 변경을 유지하고 실패 작업으로 관리한다.
- [신청 개인정보와 외부 주소 검색] → 공개 GET은 교육정보만, 성공 POST는 최소 접수 결과만 반환한다. 외부 서비스에 불필요한 입력을 전송하지 않고 SDK 예외·Q2 기록에 민감값을 노출하지 않는다.
- [브라우저 응답 유실] → 같은 request_id·입력은 기존 접수 결과를 재사용한다. 별도의 새 식별자로 반복한 신청을 이메일만으로 차단하지는 않는다.
- [의존성·환경별 차이] → Python 3.14/Django 6.1과 Q2 1.11 조합을 lock하고 실제 subprocess·개발/운영 격리 테스트로 확인한다. 현재 비교 문서의 기능 지원을 실행 검증으로 대신하지 않는다.

## Migration Plan

1. Q2 공통·django-ses 운영 의존성(events extra 제외)과 Axios 자산 설치 조합을 lock하고 settings·환경 변수·실행 문서 계약을 함께 갱신한다. 실제 `.env`·credential은 읽어 출력하거나 덮어쓰지 않는다.
2. Django makemigrations로 새 신청·안내·시도·전송 예산 모델의 추가 migration을 생성한다. 기존 education 0001/0002를 재작성하거나 DB 초기화하지 않는다. PostgreSQL 테스트 DB에서 migration·제약과 기존 프리셋 보존을 검증한다.
3. 테스트 환경에 Q2 및 앱 migration을 적용하고 스케줄 준비 명령으로 고유 주기 작업을 설정한다. API·화면·신청 저장·모의 메일·비동기 이미지 정리를 실제 worker로 검증한다.
4. 운영자는 SES verified identity·발송 권한이 있는 IAM role·rate quota와 django-ses backend 설정을 준비한 뒤 prod worker를 실행한다. SNS·웹훅·이벤트 인프라는 요구하지 않는다. 자원 생성·실발송은 별도 요청에서만 한다.
5. 운영 배포 시 이전 worker를 정상 종료하고 결과 flush를 확인한 뒤 새 코드·같은 미디어 설정의 worker를 시작한다. 유예 시간은 내부 대기까지 포함하며 서비스 관리자 설정과 함께 검증한다.
6. rollback 시 신규 신청 접수·스케줄을 먼저 중단하고 worker를 정상 종료한다. 보존된 신청·attempt·실패 기록과 대기 작업이 새 코드에 의존하므로 무조건 다운 migration하거나 옛 코드로 큐를 실행하지 않는다. 별도 검토로 재시작·복구하며 데이터를 삭제하는 rollback은 이번 자동 절차에 포함하지 않는다.
