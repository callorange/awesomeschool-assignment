# Design

## Context

동기는 [proposal.md](proposal.md), 완료 계약은 [education-presets delta](specs/education-presets/spec.md)를 따른다. 기준은 main `6abb23f`이고 기존 최대 작업 번호 010 다음인 `feature/011-add-application-presets`에서 계획한다. 이전 change는 `2026-10-23-add-application-backoffice`로 보관돼 있다.

현재 코드에서 확인한 설계 근거는 다음과 같다.

| 원자료 | 확인한 계약과 설계 영향 |
| --- | --- |
| `src/education/management/commands/seed_educations.py` | 전체 교육·이미지 입력을 검증하고 slug 기준 누락 교육만 atomic 생성한다. Storage 반환 키·실패 잔여 파일·기존 교육 보존을 유지한다. |
| `src/education/models.py` | 신청 request_id unique, 생성 때 원본 snapshot·history 저장, 생성 시각 불변. 상담은 author 필수·append-only·동일 신청 정정 검증. 안내 OneToOne, 시도 횟수 DB 상한 3, MailAttempt UUIDv7. |
| `src/education/services/applications.py` | 새 과거 연락 날짜·재연락 일정 입력과 sending 중 변경을 거부한다. 과거 상태를 준비하는 명령에 현재 시각 검증을 강제하지 않는다. 기존 관리 경로는 변경하지 않는다. |
| `src/education/serializers.py` | 공개 신규 접수는 오늘 이후·접수 활성 교육·received만 허용하며 안내 due_at은 한국 09시와 created_at 중 늦은 값이다. 샘플 때문에 API 제한을 완화하지 않는다. |
| `src/education/backoffice.py` | `-created_at, -pk` 정렬·20건, 이름/이메일 검색, snapshot 교육명 필터. today와 overdue는 겹칠 수 있고 미래 전용 필터는 없다. |
| `src/education/tasks/reminder_dispatch.py` | 도래 pending/retry_wait를 등록하고 10분 지난 queued/sending을 각각 pending/unknown으로 복구한다. |
| `src/education/tasks/reminder_delivery.py` | mode는 backend 선택값이 아니다. 실제 backend는 MAILERS 설정이며 현재 attempt_id와 시도 기록이 맞아야 결과를 저장한다. |
| `src/config/settings/{base,dev,prod}.py` | dev는 로컬 Storage, base는 simulated·locmem, prod는 DEBUG 거부·SES·S3다. DEBUG만으로 개발 여부를 판정하지 않는다. |
| `src/education/signals.py` | 교육 이미지의 저장 후 키 교체도 정리 큐를 만들 수 있다. 샘플 실행의 무큐 계약에는 이 경로도 포함한다. |
| `src/education/tests/test_presets.py`, `test_backoffice.py` | 실제 PostgreSQL·임시 미디어, 저장소 오류 주입·반환 키 보존과 실제 HTTP 필터/권한 테스트를 확장한다. |
| `openspec/specs/{education-presets,education-applications,application-management,application-notifications,application-backoffice}/spec.md` | 공개 접수와 업무 편집 계약은 유지한다. 이번 변경은 education-presets에 개발용 초기 상태 구성만 추가한다. |
| `pyproject.toml`, `uv.lock` | python-dateutil 2.9.0.post0은 현재 botocore의 간접 의존성이다. 직접 import할 예정이므로 같은 잠금 버전을 유지하며 공통 의존성에 명시한다. |
| `docs/README.md`, `docs/development.md`, `docs/architecture.md`, README와 운영·검증 가이드 | 기존 배치·검증 절차를 따른다. 검증 가이드의 2026-10-22 전체 141개 통과는 과거 기준선이다. |

## Goals / Non-Goals

**Goals:** 기존 모델의 실제 DB·history·상담 검증 경로를 사용해 평가용 상태를 준비하고 재실행은 이미 있는 신청 단위를 완전히 건너뛴다. 최초 생성의 전체 분포와 이후 담당자 편집 보존을 구분한다. 프리셋은 실제 화면과 기능을 확인할 사례를 제공하는 데 집중하고 실제 업무의 과거 사건을 세밀하게 재현하지 않는다.

**Non-Goals:** 과거 실제 상담·발송 사건의 복원, 운영 seed, reset/force/repair, 샘플 전용 UI·필터, 관리 서비스 변경, worker 예외 분기, 계정·권한 자동 설정, 새 schema와 범용 엔진을 도입하지 않는다.

## Decisions

### 1. 기존 명령에 명시적 옵션과 사전 검증 추가

선택 명령은 `uv run python src/manage.py seed_educations --with-applications --staff-user <기존 사용자명>`이다. `--staff-user`는 신청 옵션에서 필수이며 단독 지정은 사용 오류로 거부한다. `get_user_model()`의 USERNAME_FIELD로 기존 활성 staff를 찾고 선택한 계정·권한·비밀번호는 변경하지 않는다. 이 CLI의 실행 권한과 화면 모델 권한은 별개다. 화면 확인에는 기존 신청·상담·이메일 조회 권한, 편집 확인에는 신청 변경·상담 추가 권한을 별도로 준비한다. superuser 자동 탐색과 기본 비밀번호 생성은 피한다.

신청 옵션은 쓰기 전에 설정 모듈 `config.settings.dev`, `NOTIFICATION_MODE=simulated`, `MAILERS['default']['BACKEND']=django.core.mail.backends.locmem.EmailBackend`를 모두 확인한다. 운영·다른 backend는 DEBUG 값과 무관하게 거부한다. 환경 제한은 기본 교육 명령에는 추가하지 않는다. 프로세스가 개발 설정으로 운영 DB를 가리키는 것까지 자동 식별할 수 없으므로 문서에서 DB 분리를 명시한다.

### 2. 신청 데이터는 교육 프리셋 옆 고정 정의로 관리

`presets/education/application_presets.json`에 32개의 고정 request UUID, 교육 slug, 가상 입력, 상태·상대 날짜·상담·메일 사례를 둔다. UUID를 런타임 난수나 날짜로 만들지 않는다. 전용 입력 해석·생성 함수는 기존 command 안에 두고 공개 service·범용 preset registry는 만들지 않는다. 원본 교육 JSON·이미지·출처 기록은 변경할 이유가 없다.

메일 검색 접두어는 `application-preset-`, 이메일은 `application-preset-01@example.com`부터 32까지, 이름은 `샘플 신청자 01` 형식, 주소는 `가상시 샘플구 예시로 01` 등 명백한 가상 주소와 숫자 5자리 우편번호를 사용한다. 상담 내용에도 `[샘플]`을 붙인다. 기존 교육은 slug로 재사용하고 신청 당시 교육명은 그 실행에서 연결한 교육의 현재 title을 snapshot으로 저장한다. 닫힌 교육에도 과거 신청을 준비할 수 있으며 접수 활성값을 바꾸지 않는다.

### 3. 고정 순서와 기준 시각으로 혼합 구성

번호는 최신순이다. 교육은 기존 교육 JSON의 `prompt-hero`, `emotion-hero`, `relationship-hero` 순환으로 배정한다.

상태별 번호를 다음과 같이 고정한다. 각 교육 총수는 11·11·10이고 두 페이지 모두 세 교육과 다섯 상태가 나타난다. 무작위 shuffle이나 상태별 일괄 접수 시각 배정은 사용하지 않는다.

| 상태 | 번호 |
| --- | --- |
| received | 01, 06, 12, 15, 20, 23, 28, 31 |
| consulting | 02, 08, 13, 19, 26, 30 |
| follow_up | 03, 07, 11, 14, 18, 21, 24, 27, 29, 32 |
| completed | 04, 10, 17, 25 |
| cancelled | 05, 09, 16, 22 |

호출 시작 시 Django `timezone.now()`를 한 번 호출하고 `timezone.localtime()`으로 한국 시각의 aware 기준값 now와 날짜 T를 확보한다. 상대 날짜 계산은 `dateutil.relativedelta.relativedelta`를 사용한다. 예를 들어 번호 i(0부터)의 접수 시각은 `now - relativedelta(days=i, hours=2)`로 분산할 수 있다. 정확한 시·분과 간격은 제품 계약이 아니며 미래 접수 방지·최신순 혼합·화면 사례 구성이 충족되면 구현에서 간단히 정한다.

설치 패키지명은 `python-dateutil`, import 경로는 `dateutil.relativedelta`다. 이미 uv.lock에 있는 버전을 재사용하되 운영 패키지 설치 여부에 기대지 않도록 pyproject.toml 공통 의존성에 직접 명시하고 lock metadata를 동기화한다. 별도 날짜 wrapper·문자열 날짜 parser·범용 상대 날짜 DSL은 만들지 않는다. Django timezone은 기준 시각과 시간대를, relativedelta는 상대 이동을 담당한다. 공식 문서의 복수형 `days`·`hours`는 상대 이동, 단수형 `hour`·`minute`은 값 지정이라는 구분을 따른다: [relativedelta 문서](https://dateutil.readthedocs.io/en/stable/relativedelta.html), [PyPI](https://pypi.org/project/python-dateutil/).

연락 날짜는 기준일 offset으로 해석하되 `max(접수 한국 날짜, T + offset)`을 사용한다. pending에 과거·오늘·미래 날짜를 배분하고, 발송 시도 사례는 과거 연락 날짜를 사용해 새벽 실행에도 due_at이 현재보다 늦지 않게 한다. due_at 계산은 공개 접수와 같은 `max(연락 날짜 한국 09시, created_at)`이다. 날짜별 고정 캘린더 값을 쓰지 않는다.

재연락 03·07·11은 오늘, 14·18·21은 과거, 24·27은 미래, 29·32는 None으로 구성한다. 예를 들어 `now + relativedelta(days=1, hour=14, minute=0, second=0, microsecond=0)`으로 내일 오후를 정할 수 있다. 개별 시각은 고정 계약으로 두지 않고 모두 해당 접수 후가 되도록 정한다. today는 3건이고 overdue는 지난 날짜 3건에 현재보다 이른 오늘 일정을 더하므로 항상 3건이라고 단정하지 않는다. follow_up 외 next_contact_at은 None, 취소는 사유 필수다.

### 4. 최초 생성과 관리 변경 경로를 구분

공개 serializer나 `save_application()`을 호출해 과거 날짜 제한을 우회시키지 않는다. 새 샘플만 command에서 모델 field 검증과 위 관계 검증 후 최종 상태로 생성한다. `EducationApplication.full_clean()`은 save가 생성하는 submission_snapshot을 제외하고 호출하고, 일반 `save()`로 최초 snapshot과 생성 history를 남긴다. bulk_create·update·직접 SQL로 이력을 건너뛰지 않는다.

history는 초기 생성 한 건을 기록하고 `_history_user=None`, 샘플 초기화라는 change reason, `_history_date=created_at`으로 합성 초기 상태임을 구별한다. 선택한 staff가 과거에 실제로 상태를 변경했다는 가짜 전이 이력은 만들지 않는다. 이후 실제 담당자 변경은 기존 서비스가 실제 변경자·시각으로 기록한다.

received에는 상담이 없는 사례를 두고 나머지에 상담 진행·부재중·재연락 합의를 배분한다. 여러 상담의 시각은 접수부터 now 사이의 증가하는 지점으로 정한다. 대표 follow_up에는 부재중→재연락 합의를, 대표 consulting에는 원문→정정을 만든다. 정정은 동일 신청에서 먼저 만든 원기록을 참조하고 `ConsultationRecord.save()`의 full_clean을 사용한다. 상담의 next_contact_at은 각 기록 당시 합의한 일정이며 현재 신청 일정과 항상 같아야 하는 값은 아니다. 이미 기한이 지난 재연락 합의는 해당 일정 이전에 상담한 것으로 구성한다. 입력에서 원기록 순서·시각·일정 관계도 검증한다.

### 5. 메일은 화면 확인용 합성 상태, SES 증거 없음

accepted는 SES 응답을 근거로 하는 계약과 충돌하므로 생성하지 않는다. 기존 `test_backoffice.py`의 accepted 렌더링 검사와 별도 opt-in 실제 SES 검증은 유지한다. 샘플 상태를 실제 task 실행 결과로 기록하기 위해 발송 함수를 부르지 않는다.

| 안내 상태 | 번호 | 구성 |
| --- | --- | --- |
| pending | 01, 06, 12, 15, 20, 23, 28, 31 | 횟수 0, 시도·queued_at·started_at·완료 시각 없음 |
| queued | 02, 08, 13 | 최초 큐 대기 표시만 구성, 횟수 0·시도 없음, queued_at 있음, 실제 Q2 row 없음 |
| sending | 19, 26 | 횟수 1, 현재 MailAttempt·started_at, finished_at 없음 |
| simulated | 03, 07, 11, 14, 04, 10, 30 | 횟수 1, 완료 시도·simulated_at |
| retry_wait | 18, 21, 24 | 횟수 1, 완료 시도·안전한 오류 코드·next_retry_at |
| failed | 17, 27 | 횟수 1, 완료 시도·안전한 오류 코드 |
| unknown | 05, 29, 32 | 횟수 1, 완료 시도·결과 불명 코드 |
| suppressed | 09, 16, 22, 25 | 미시도 종료, 횟수 0·시도 없음 |

모든 mode는 simulated이고 sent_at은 None, ses_message_id는 빈 문자열이다. 완료·취소에는 pending/queued/sending/retry_wait를 배정하지 않는다. 일부 종료에는 이미 처리된 simulated/failed/unknown 증거를 남겨 실제 관리 계약과 맞춘다. 합성 오류 코드는 `preset_simulated_failure`·`preset_simulated_retry`·`preset_simulated_unknown` 등 외부 오류 원문이 아닌 코드로 식별한다.

시도는 기존 default UUIDv7로 생성하고 attempt_count는 연결 시도 수, attempt_id는 최근 시도 PK, started_at은 해당 시도의 시작과 일치시킨다. 처리 시각은 `created_at <= due_at <= started_at <= finished_at/simulated_at <= now`를 만족하도록 유효 구간 안에서 배분한다. sending은 종료 시각이 없고 queued_at은 due_at부터 now 사이로 둔다. retry_wait는 완료 후 허용 시각을 두며 도래·미도래 사례를 함께 포함한다. MailSendBudget과 Q2 Schedule/OrmQ는 만들거나 갱신하지 않는다.

### 6. 신청 단위 재실행 건너뜀과 전체 atomic 경계

기존 request_id가 있으면 불변 submission_snapshot의 샘플 이메일·교육 slug로 식별 충돌만 확인한 뒤 신청 전체를 건너뛴다. 현재 이메일·이름·상태·교육 연결이 바뀌어도 보존한다. 기존 날짜는 기준일이 달라졌다는 이유로 비교·재계산하지 않는다. 없는 안내나 상담을 보완하는 repair는 하지 않는다. 일부 샘플만 존재하면 없는 샘플만 현재 기준으로 생성하므로 전체가 동일 기준일이라는 보장은 최초 완전 생성에 한정한다.

환경·담당자·원본 구조·중복 UUID·분포·관계 검증 후 기존 교육 atomic 블록을 확장해 누락 교육, 신규 신청·상담·안내·시도·history를 함께 저장한다. request_id unique와 안내 OneToOne을 사용하고 기존 get_or_create 패턴으로 재실행 중복을 막는다. 종속 기록은 신청이 실제 생성된 경우에만 만든다. DB 오류는 atomic 블록 밖에서 CommandError로 보고하고 commit 후 건수를 출력한다.

교육 이미지의 반환 키가 달라져 두 번째 save가 일어나면 기존 signal이 정리 큐를 만들 수 있다. 신규 교육에 한해 Storage의 실제 반환 키를 확정한 뒤 최초 DB 저장하도록 순서를 정리해 큐 등록을 없앤다. 기존 교육은 저장하지 않는다. 기본 교육 명령의 파일명·반환 키·실패 시 DB 롤백·잔여 파일 안내는 보존하고 test_presets의 기존 반환 키·실패 테스트로 회귀를 확인한다. 이로써 no-queue는 메일뿐 아니라 이미지 정리에도 적용된다. DB rollback 때 파일을 자동 삭제하는 보상 작업은 추가하지 않는다.

### 7. 검증은 자동 테스트·DB 제약·브라우저가 나누어 보증

| 수단 | 관찰할 결과 |
| --- | --- |
| PostgreSQL 제약 | request_id 중복 거부, 안내 OneToOne, author/정정 FK, 시도 횟수 상한 3. 날짜·시도 일치는 기존 DB 제약에 없으므로 명령 검증·테스트로 보증한다. |
| `test_presets.py` 확장 | 정확히 32건·상태/교육/메일 분포, 두 페이지의 혼합, 한국 날짜 경계의 대표 사례, 상담/정정/시도의 선후 관계, 재실행 전체 snapshot 보존, 일부 존재·식별 충돌, invalid author/settings, 중간 저장·history 실패 rollback. 날짜 라이브러리 자체의 월말·윤년 연산이나 임의 시·분 조합은 재검증하지 않는다. |
| 외부 경계 격리 | 메일 send·큐 async_task를 mock하여 호출 없음 확인, 실제 OrmQ·Schedule·MailSendBudget 건수/내용 불변 비교. DB·history·상담 저장 자체를 mock으로 우회하지 않는다. |
| `test_backoffice.py` 확장 | 명령으로 만든 실제 샘플을 기존 권한별 client에서 20·12건, 이름/이메일 검색, 교육·상태·재연락 필터, 조건 보존 링크와 대표 상세/이메일 partial로 확인. 일반 신청 공존도 확인한다. |
| 브라우저 | 격리 PostgreSQL DB·임시 미디어·loopback 서버에서 기존 staff를 명시해 샘플 준비 후 목록·두 페이지·대표 상세·수동 상태 새로고침을 360/390/768/1280px에서 확인한다. HTML 검사로 대체하지 않는다. |

명령은 먼저 `uv run python src/manage.py test education.tests.test_presets education.tests.test_pages education.tests.test_backoffice`를 사용한다. 공통 교육 저장 순서를 바꾸므로 안정화 후 `test education` 전체와 Django check·migration 누락·Ruff lint/format도 수행한다. 실제 결과와 미검증 환경은 검증 가이드에 기록하고 141개 기준선을 새 결과로 복사하지 않는다.

## Risks / Trade-offs

- [worker가 화면용 상태를 변경] → 생성과 최초 브라우저 확인 때 qcluster·다른 등록 프로세스를 중지한다. 조회만 하는 email partial은 상태를 바꾸지 않는다. 이후 별도 검증에서 worker를 시작하면 도래 pending/retry_wait는 모의 완료로 진행하고 합성 queued는 실제 task가 없으므로 10분 만료 후 복구·재등록, 합성 sending은 10분 만료 후 unknown으로 바뀐다. 종료·완료 증거는 기존 정책대로 보존한다. 재실행은 상태 복원 수단이 아니다.
- [상태명만 보면 실제 처리로 오해] → 샘플 이름·이메일·상담·오류 코드와 운영/검증 가이드에 합성 상태를 명시하고 실제 SES 접수 증거를 만들지 않는다. 이 명령은 외부 전달 증명의 도구가 아니다.
- [날짜가 지나 분포가 달라짐] → 최초 생성일 분포만 보장한다. 재실행에서 날짜를 이동시키지 않는다. 새 기준일 확인은 별도 격리 환경에서 수행하고 개발 DB를 reset하지 않는다.
- [담당자 FK와 삭제 보존] → 기존 계정을 명시해야 하며 상담 작성자로 연결된 계정은 기존 PROTECT 정책에 따라 삭제 대신 비활성화한다. 이 효과를 실행 안내에 포함한다.
- [기존 데이터가 있으면 목록이 20·12가 아님] → 기존 데이터는 유지하고 샘플 이메일 접두어 검색으로 확인한다. 교육명을 바꾼 환경은 현재 snapshot 기준으로 검색한다.
- [DB transaction 밖 미디어 쓰기] → 기존 잔여 파일 안내와 재사용을 유지한다. 파일 삭제나 완전한 파일·DB 동시 rollback을 약속하지 않는다.

## Migration Plan

schema migration은 없다. apply 단계에서 관련 언어·framework 규칙을 읽고 위 범위만 구현한다. README의 기본 실행은 유지하고 선택 샘플 절차는 계정 준비→worker 중지→옵션 명령→두 페이지/대표 상세 확인→필요 시 worker 시작 순서로 추가한다. `docs/guides/operations.md`에 환경·계정·합성 상태·보존과 worker 효과를, `docs/guides/verification.md`에 실제 검증 증거를 기록하고 `docs/architecture.md`의 프리셋 책임 설명만 동기화한다.

적용을 되돌려도 이미 생성된 신청은 보존한다. 코드 철회와 데이터 삭제는 분리하며 초기화·삭제 명령을 추가하지 않는다. 이번 propose 단계는 artifact만 작성하고 DB·미디어 생성이나 테스트 실행을 하지 않는다.
