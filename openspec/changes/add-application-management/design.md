# Design

## Context

배경과 범위는 [proposal.md](proposal.md)를 따른다. 직접 작성한 앱은 `education` 하나이며 `admin.py`는 비어 있다. Django 인증·admin·CSRF와 Q2 자체 admin은 이미 설정되어 있다.

`Application.Status`에는 received만 있고 `ApplicationSerializer._reuse()`는 현재 모델 필드와 최초 제출을 직접 비교한다. 공개 API도 현재 `application.status`를 반환하므로 상태 추가만 하면 기존 접수 응답 명세가 깨진다. 안내는 신청과 OneToOne이며 연락 가능 날짜를 바탕으로 `due_at`을 생성한다. `claim()`이 안내와 신청을 읽어 sending을 확정한 뒤 외부 호출은 lock 밖에서 실행한다.

관련 계약은 `specs/application-management`, `specs/education-administration`, `specs/education-applications`, `specs/application-notifications` delta를 따른다. 기존 명세의 공개 신청 조회 금지와 사용자 요청의 관리자 조회는 접근 경계가 다르므로 함께 유지한다. 원문 CRUD 중 삭제는 사용자의 보존 요구를 우선하며 별도 논리 삭제 모델을 만들지 않는다.

## Goals / Non-Goals

**Goals:**
- 기본 admin과 기존 ORM·폼·transaction 구조를 활용해 관리 경로를 좁게 유지한다.
- 최초 제출, 현재 관리값, 누적 상담 기록, 신청 변경 이력, 메일 처리 기록의 책임을 구분한다.
- 새 권한 경계와 안내 처리권의 실제 경합을 테스트 가능한 계약으로 정한다.

**Non-Goals:**
- 별도 백오피스·관리 API·프런트 번들·상태 머신 패키지·범용 감사 프레임워크를 만들지 않는다.
- DB 관리자나 직접 SQL까지 차단하는 변조 방지·영구 보존 시스템을 보장하지 않는다.
- 과거 상태 복원, 운영 개인정보 삭제 정책, 알림·캘린더·담당자 배정은 구현하지 않는다.

## Decisions

### 1. 기본 admin과 모델별 권한

새 전용 UI보다 기존 로그인·CSRF·모델 권한을 활용한다. 활성 staff이면서 해당 모델 권한을 가진 사용자가 작업하며 superuser도 기능상 삭제·이력 복원 금지는 우회하지 못한다.

| 모델 | 화면과 작업 |
| --- | --- |
| Education | 목록·검색·필터·등록·수정. 이번 화면의 삭제 동작은 비활성화 |
| Application | 목록·상세·정정·상태·일정·이력 조회. 추가·삭제·일괄 상태 변경 없음 |
| ConsultationRecord — 신규 | 신청별 누적 기록 추가·조회. 기존 기록 변경·삭제 없음 |
| ApplicationNotification / MailAttempt / MailSendBudget | 별도 조회 전용 등록. 관련 권한 없이 신청 상세의 안내 정보도 공개하지 않음 |

기본 User·Group과 Q2 등록은 유지하며 sessions·contenttypes 같은 프레임워크 내부 모델을 새로 노출하지 않는다. 신청 목록은 이름·이메일 검색, 교육 snapshot·상태·연락 날짜·재연락 분류 필터와 기본 pagination을 사용한다. 상세 관련 데이터 조회는 실제 사용 관계만 함께 조회한다.

### 2. 현재 상태와 누적 상담 기록

Application에 `consulting`(상담중), `follow_up`(재연락 예정), `completed`(완료), `cancelled`(취소)를 추가하고 received는 유지한다. nullable `next_contact_at`과 취소 사유를 추가한다. 취소 사유는 취소로 진입할 때 필수이며 수정 이력으로 보존한다. 다른 상태로 되돌릴 때 현재 취소 사유는 비우고 이력에는 남긴다. 별도 상태 전이 엔진이나 자동 종료 규칙은 두지 않는다.

다음 연락 예정은 follow_up에서만 허용하며 미정(null)도 가능하다. 새로 지정·변경한 과거 일정은 거부하되 기존 기한 경과 값을 유지한 다른 정정은 허용한다. 오늘/기한 경과는 한국 시각의 현재 날짜·시각 기준으로 분류하며 오늘 중 이미 지난 일정은 두 필터에 포함될 수 있다. 미정 필터는 follow_up이면서 null인 경우다.

ConsultationRecord는 신청 FK, 작성자, 작성 시각, 결과(상담 진행·부재중·재연락 합의·정정), 필수 내용, 당시 next_contact_at snapshot, 선택적 정정 대상 self FK를 저장한다. 작성자·시각·신청 연결은 서버에서 지정한다. 정정은 같은 신청의 원기록을 지정하게 한다. 작성자 참조는 PROTECT로 기록이 있는 계정의 삭제를 막고 계정 비활성화를 사용한다.

신청 상세에서 관련 상담 기록을 읽고 새 기록을 추가할 수 있게 한다. 결과 선택만으로 상태를 자동 변경하지 않는다. 상태·일정만 변경한 경우 이력이 해당 변경을 추적하므로 상담 메모를 강제 생성하지 않으며, 취소에는 사유를 요구한다. 신청과 상담 기록을 함께 제출하면 동일 transaction에 저장한다.

신청과 상담의 admin 삭제 URL·delete_selected·수정 form 우회를 차단한다. 모델 instance와 QuerySet의 일반 삭제 경로도 차단하고 상담은 신청 FK를 PROTECT로 둔다. 최초 원본과 기존 상담의 불변조건은 프로젝트가 제공하는 저장 경로에서 지킨다. 직접 SQL·과거 migration·외부 DB 도구에 대한 보장은 하지 않는다.

### 3. 변경 이력은 django-simple-history

현재 Python 3.14·Django 6.1 조합을 명시적으로 지원하는 `django-simple-history` 3.13 계열을 공통 의존성으로 사용한다. 설정·앱 등록과 필요한 사용자 추적을 연결하고 Application에만 HistoricalRecords를 적용한다. 직접 diff 테이블을 만들거나 호환성 확인이 추가로 필요한 django-auditlog를 선택하지 않는다.

SimpleHistoryAdmin으로 전후 값·시각·사용자를 조회하되 복원 UI와 직접 복원 요청을 차단한다. 이력 조회는 신청 조회 권한을 필요로 하며 historical 모델을 별도 쓰기 가능한 admin으로 등록하지 않는다. 최초 제출 snapshot은 이력 대상에서 제외해 같은 개인정보의 불필요한 중복을 줄인다. 현재 신청의 교육 FK 해제 같은 시스템 변경에는 사용자 없음과 변경 사유를 구분한다. 사용자 추적이 없는 외부 작업자를 특정 관리자처럼 표시하지 않는다.

신청 일괄 상태 action이나 QuerySet.update/bulk_update를 새 관리 경로에 사용하지 않는다. 기존 교육 삭제의 SET_NULL은 Django Collector가 signal 없이 갱신할 수 있으므로, 연결 신청을 삭제 transaction 안에서 이력 지원 저장으로 먼저 해제하고 history를 남기도록 기존 교육 삭제 signal과 직접 영향 범위를 확인한다. 안내 worker의 상태 변화는 Application 이력 대상이 아니며 기존 MailAttempt가 담당한다.

패키지의 생성/변경 history도 해당 신청 transaction과 함께 rollback되어야 한다. 저장 실패 시 변경만 남는지 실제 DB 테스트로 확인한다. 교육 자체·내부 안내 모델의 범용 이력은 추가하지 않는다.

### 4. 최초 제출과 현재 관리값 분리

Application에 관리자에게 읽기 전용인 최초 정규화 제출 JSON snapshot을 둔다. 정규화 규칙은 기존 serializer를 재사용하고 날짜·UUID는 안정된 문자열 형태로 직렬화한다. request_id는 기존 고유 필드로 유지하며 snapshot에는 비교에 필요한 education_slug·이름·이메일·주소·날짜를 보관한다. 현재 교육명을 바꾸거나 신청 정보를 정정해도 snapshot은 바꾸지 않는다.

`_reuse()`는 snapshot을 비교해 기존 접수만 재사용한다. 공개 API 응답은 항상 received/접수와 request_id로 제한한다. admin의 취소나 재연락 상태를 공개 재시도 응답에 포함하지 않는다. snapshot은 이력의 가장 오래된 row에서 매번 복구하는 방식보다 명시적이며 history 삭제·초기 backfill에 의존하지 않는다.

관리 연락 가능 날짜는 재연락 일정으로 덮어쓰지 않는다. 실제 오입력 정정은 허용하되 새 값은 오늘 이후여야 하고 과거 신청의 변하지 않은 날짜는 허용한다. 신청 당시 교육 snapshot·교육 연결·request_id·created_at을 관리 입력에서 변경하지 않는다.

### 5. 안내 처리권과 관리 변경의 일관성

관리 저장과 worker claim이 같은 안내 row lock을 먼저 얻도록 맞추고 필요한 신청 lock 순서도 안내 → 신청으로 통일한다. 저장 직전에 최신 상태를 재검증하며 오래 열린 form의 값만 믿지 않는다. 이 경계는 별도 범용 계층보다 작고 명확한 관리 저장 연산 하나로 묶고 admin에서 호출한다.

| 안내 상태 | 신청 이름·이메일·연락 날짜 정정 | 완료·취소 |
| --- | --- | --- |
| pending / queued / retry_wait | 최신 값 사용. 날짜 정정 시 due_at을 max(연락 날짜 09시, created_at)으로 함께 변경 | suppressed(발송 중단)로 기록 |
| sending | 해당 필드 수정 거부. 주소·상담 기록·재연락 일정 같은 발송 무관 변경은 허용 | 거부하고 결과/만료 복구 이후 다시 처리하도록 안내 |
| accepted / simulated / unknown / failed / suppressed | 신청 정정만 허용. 기존 안내 결과 유지, 새 발송 없음 | 종료 상태만 저장. 안내 증거 유지 |

suppressed는 완료·취소에 의한 미처리 안내 중단으로 표시하고 기존 시도·횟수를 남긴다. queued_at·next_retry_at은 해제하며 복구 검사·등록·claim·후속 검사 모두 중단 상태와 종료 신청을 제외한다. 이미 Q2에 들어간 작업을 제거하는 대신 실행 시 전송을 건너뛴다. 날짜 변경으로 아직 이르다면 claim이 시도 생성 전에 거부하고 queued 작업은 기존 stale 복구 후 새 시각에 다시 발견된다.

날짜·수신자를 정정해도 시도 횟수·재시도 허용 시각·전송 모드는 초기화하지 않는다. 이름과 날짜도 메일 본문에 사용하므로 sending 변경 제한에 포함한다. sending 뒤 실제 외부 호출을 되돌릴 수 없으므로 취소 성공인 것처럼 기록하는 대안은 사용하지 않는다. 기존 10분 stale sending 복구·unknown 처리·늦은 성공 기록 계약은 유지한다.

다음 연락 예정은 메일 due_at에 영향을 주지 않는다. 종료 후 다시 활성 상태로 바꿔도 suppressed·accepted·unknown 등을 자동 재개하거나 재발송하지 않는다. 수동 재발송 기능은 이번 범위에 없다.

### 6. 교육 편집과 기존 입력 검증

EducationAdmin은 ModelForm의 기존 모델 validator를 사용해 목표·대상·커리큘럼 구조를 검증하고 이미지 수정은 일반 save 경로를 유지한다. media_id는 읽기 전용이다. 새 JSON 편집기 패키지나 일괄 편집·교육 이력은 도입하지 않는다. 기존 이미지 교체·교육 삭제 signal과 큐 rollback 테스트를 유지한다.

## Risks / Trade-offs

- [과제 원문은 삭제를 요구함] → 사용자 요청의 보존을 우선하고 README에 차이를 명시한다. 논리 삭제·보관 버튼을 삭제의 대체 기능처럼 추가하지 않는다.
- [이력에도 과거 이메일·주소가 남음] → 신청 조회와 동일한 권한 경계, 공개 응답·task 로그 제외, snapshot의 추가 이력 제외. 무기한 보존의 운영 정책은 별도 결정이다.
- [패키지가 모든 쓰기를 포착하지 않음] → 관리 변경과 교육 FK 해제 경로를 명시하고 실제 DB 테스트로 기록을 확인한다. 직접 SQL 감시는 범위 밖이다.
- [sending 중 종료가 바로 되지 않음] → 발송 상태와 재시도 안내를 표시한다. 결과 또는 기존 만료 복구를 기다리며 성공한 취소로 오인시키지 않는다.
- [권한 구현 오류로 개인정보·기록이 노출될 수 있음] → 비로그인·일반 사용자·권한 없는 staff·조회 전용·편집 권한·superuser의 URL/POST 우회 테스트를 수행하고 구현 후 권한 경계를 별도 관점으로 검토한다.
- [교육 이미지 업로드 후 DB rollback은 고아 파일을 남길 수 있음] → 기존 파일 정책을 유지하며 저장소 전수 정리로 범위를 확대하지 않는다.

## Migration Plan

1. `django-simple-history` 공통 의존성과 설정을 추가하고 기존 migration은 보존한다. 모델에 nullable 원본 snapshot·일정·취소 사유, 상담·history 테이블과 새 상태를 추가한다.
2. 기존 신청의 현재 값을 최초 제출 snapshot으로 batch backfill한다. 현재는 관리 기능이 없으므로 이 값을 기준으로 삼되 과거 수동 DB 정정이 있었다면 원래 입력을 복원할 수 없다는 한계를 명시한다. 기존 신청마다 도입 시점의 기준 history를 남기고 과거 변경자·시각을 만들어내지 않는다.
3. schema 변경과 backfill은 검토 가능한 후속 migration으로 나누고, 데이터 migration은 historical model을 사용한다. 직접 SQL dump·DB 초기화·volume 삭제는 사용하지 않는다. snapshot 완전성 검증 뒤 신규 생성 필수·읽기 전용 계약을 적용한다.
4. 기존 신청·교육·안내·시도 보존, 신규 생성·backfill 후 재시도, rollback의 범위를 PostgreSQL 테스트 DB로 검증한다. 운영 적용은 web/worker를 멈춘 maintenance 방식으로 계획하고 무중단 적용을 주장하지 않는다.
5. 신규 관리 기록이 쌓인 뒤 migration 역적용은 이력 손실을 일으키므로 기본 rollback은 새 관리 쓰기 중단과 데이터·schema 보존 후 전진 수정이다. 구 코드로 돌아가면 새 상태를 이해하지 못하므로 전체 버전 rollback은 별도 데이터 검토 없이는 수행하지 않는다.

공식 참고: [지원 버전](https://pypi.org/project/django-simple-history/), [admin 연동](https://django-simple-history.readthedocs.io/en/stable/admin.html), [일괄 갱신 제한](https://django-simple-history.readthedocs.io/en/stable/common_issues.html).
