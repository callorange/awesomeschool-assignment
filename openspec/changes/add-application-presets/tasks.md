# Tasks

이번 propose에서는 아래 작업을 실행하지 않는다. 별도 apply 요청 이후 같은 브랜치에서 구현하며 실제 개발 DB에 샘플을 생성하는 작업은 이 체크리스트의 검증에 포함하지 않는다.

## 1. 고정 샘플 정의와 입력 검증

- [ ] 1.1 `presets/education/application_presets.json`에 design의 번호·교육 순환·상태 배분과 가상 개인정보·고정 request UUID 32개를 정의한다. command 내부 전용 로더와 `test_presets.py`의 유효/잘못된 입력 사례를 함께 추가하고 32건·UUID 유일성·교육 11/11/10·상태 8/6/10/4/4·두 페이지 혼합과 example.com 사용을 assertion으로 확인한다.
- [ ] 1.2 기존 lockfile의 `python-dateutil` 버전을 유지해 공통 직접 의존성으로 명시하고 lock metadata를 동기화한다. Django timezone으로 실행당 하나의 한국 시각 기준값을 잡고 relativedelta로 접수·연락·재연락·상담·메일 시각을 계산한다. 실제 날짜 관계와 한국/UTC 날짜가 다른 대표 시점에서 미래 접수 없음, 접수 이후 연락 날짜·상담, 재연락 3/3/2/2와 메일 시각 순서를 test_presets로 확인한다. 라이브러리 자체의 월말·윤년 검증과 전용 날짜 엔진은 추가하지 않는다. `docs/architecture.md`에 의존성 재사용·데이터 위치·최초 날짜 계산 책임을 동기화한다.

## 2. 옵션·환경·담당자와 기본 명령 호환성

- [ ] 2.1 `seed_educations`에 `--with-applications`와 `--staff-user`를 추가하고 신청 옵션은 dev 설정·simulated 모드·locmem backend와 기존 활성 staff를 쓰기 전에 확인한다. 누락/단독 옵션·미존재/비활성/non-staff·prod/SES/다른 backend를 test_presets에서 거부하고 DB·임시 미디어·계정/권한 불변을 확인한다. README에 기존 계정을 명시하는 선택 명령과 기본 교육 명령 유지 여부를 설명한다.
- [ ] 2.2 신규 교육 이미지의 Storage 실제 반환 키를 최초 DB 저장에 사용하여 이미지 정리 큐를 유발하지 않게 한다. 기존 기본 명령·운영 저장소 계약·기존 교육/이미지 보존·파일 재사용·반환 키/저장소 실패 테스트를 유지하고, 조정된 반환 키에서도 async_task 호출과 실제 큐 증가가 없음을 검증한다. 운영 가이드의 DB rollback 후 파일 잔여 안내를 유지한다.

## 3. 원자적 신청·상담·메일 저장과 재실행 보존

- [ ] 3.1 교육과 같은 atomic 경계에서 새 신청을 모델 검증·일반 save로 생성해 원본 snapshot·초기 history를 보존한다. history의 시스템 작성자·샘플 사유·생성 시각을 확인하고, 공개 serializer와 관리 저장 서비스의 과거 날짜 제한을 변경하지 않았는지 기존 API/신청 관리 테스트로 검증한다. docs/architecture에 최초 샘플 생성과 업무 변경 경로의 차이를 기록한다.
- [ ] 3.2 지정 staff의 상담 없음·복수 상담·부재중→재연락 합의·원문→정정 사례를 생성한다. test_presets에서 작성자·시간 순서·당시 일정·같은 신청 정정 연결과 원문 보존, 취소 사유·종료 상태의 현재 일정 비움을 실제 ORM 조회로 확인한다. 운영 가이드에 상담 author 연결 후 계정 삭제 제한과 기존 화면 권한 준비를 설명한다.
- [ ] 3.3 design의 8종 이메일 상태와 연결 MailAttempt를 생성한다. test_presets에서 모든 mode=simulated, accepted/SES 시각/MessageId 없음, 상태별 시도 수·현재 attempt_id·시작/종료/재시도 시각, 종료 상태와 대기 상태 모순 없음을 검증한다. 메일 발송/큐 경계 호출 없음과 기존 OrmQ·Schedule·MailSendBudget 내용 불변을 함께 확인한다. 운영·검증 가이드에 합성 상태와 실제 처리 증거의 차이를 명시한다.
- [ ] 3.4 고정 request_id로 새 신청만 만들고 기존 신청은 불변 snapshot의 샘플 이메일·교육 slug 충돌 확인 후 종속 기록까지 건너뛴다. 담당자 이름/이메일/주소/상태/일정 정정·상담 추가 후 다른 날 재실행하여 신청·snapshot·상담·안내·시도·history 전체 snapshot이 동일하고 생성 0/건너뜀 32임을 확인한다. 일부 존재 시 누락분만 추가하고 식별 충돌은 실패하며 일반 신청·교육·계정·파일을 보존하는 검사를 추가한다. README·운영 가이드에 날짜와 상태를 재설정하지 않는 계약을 기록한다.
- [ ] 3.5 전체 저장 중 상담/안내/시도/history/DB 오류를 주입하여 해당 실행의 교육·신청·종속 데이터 전체 rollback과 기존 데이터 보존을 실제 PostgreSQL 테스트에서 확인한다. 잘못된 관계 입력은 성공으로 처리하지 않고 파일 쓰기 전 확인 가능한 오류는 선검증함을 확인한다. 실패 메시지의 잔여 파일 안내·개인정보 비노출과 성공 commit 후 교육/신청별 건수 출력을 assertion으로 검증한다.

## 4. 백오피스 통합과 실제 화면 검증

- [ ] 4.1 `test_backoffice.py`에 실제 명령으로 준비한 샘플 조회 검사를 추가한다. 샘플만 있는 DB의 20/12건·중복/누락 없음·각 페이지 교육/상태 혼합, 이름/이메일 검색·교육/상태/재연락 필터·링크 조건 보존과 대표 상세/이메일 partial을 확인한다. today/overdue 중첩은 현재 시각으로 예상값을 계산하고 일반 신청 공존 시 이메일 접두어 검색으로 32건을 분리한다. 검증 가이드에 대표 번호·조회 순서를 추가한다.
- [ ] 4.2 별도 PostgreSQL 테스트 DB·임시 미디어·기존 테스트 staff와 loopback 서버를 준비하고 worker가 없는 상태에서 실제 브라우저로 360/390/768/1280px의 목록 두 페이지·검색/필터·상담 없음/복수/정정·종료 사유·8종 메일 상태와 수동 새로고침을 확인한다. 기존 개발 DB와 미디어를 사용하지 않으며 브라우저 결과·미검증 환경을 검증 가이드에 기록한다.
- [ ] 4.3 초기 화면 확인 후 격리 테스트 환경에서 기존 등록/복구 task로 도래 pending/retry_wait 처리, 만료 queued 재등록, sending→unknown, 종료 대상 제외를 검증한다. 새 worker 분기 없이 실제 DB 상태 변화를 확인하고 mock/locmem 경계로 외부 발송 없음을 검증한다. 운영·검증 문서에 worker 시작 전 확인 순서와 이후 재실행으로 원래 상태가 복구되지 않는 점을 동기화한다.

## 5. 최종 통합 검사

- [ ] 5.1 `uv run python src/manage.py test education.tests.test_presets education.tests.test_pages education.tests.test_backoffice` 통과 후 `uv run python src/manage.py test education`, `check`, `makemigrations --check --dry-run`, `uv run ruff check .`, `uv run ruff format --check .`, `git diff --check`를 실행한다. 모든 DB 검증은 PostgreSQL 테스트 DB에서 수행하고 실제 결과·실패 원인·미검증 한계를 검증 가이드에 기록한다. 기존 141개 기록을 이번 실행 결과로 대체하지 않는다.
- [ ] 5.2 README·아키텍처·운영·검증 문서의 옵션·기본 동작·계정 준비·데이터 보존·합성 상태·worker 순서를 코드/테스트와 대조하고 링크·명령을 확인한다. `openspec validate add-application-presets --strict`와 diff로 이 change 범위의 계약·검증 증거가 일치하고 python-dateutil 직접 의존성 명시 외에 불필요한 패키지·모델 필드·migration·계정 생성·초기화 옵션이 추가되지 않았음을 확인한다.
