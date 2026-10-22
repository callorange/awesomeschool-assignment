# Proposal

## Why

현재 교육 소개와 접수 가능 여부는 제공하지만 방문자가 상담 신청을 제출할 수 없다. 교육 신청을 접수 상태로 보존하고, 모바일에서도 입력·주소 검색·비동기 제출을 완료하게 하며 날짜에 따른 안내와 이미지 정리를 요청 처리에서 분리한다.

## What Changes

- 교육별 반응형 신청 페이지와 이름·이메일·주소·연락 가능 날짜 입력을 추가한다. Axios로 교육정보 GET과 신청 POST를 호출하고 Kakao 우편번호 검색을 폼 안에 삽입한다.
- DRF 공개 교육정보 GET과 신청 생성 POST를 제공한다. 신청·안내 대상은 PostgreSQL에 함께 저장하며 신규 상태는 서버에서 `접수`로 지정하고 완료 화면에 표시한다. 공개 신청 목록·개인정보 조회와 상태 변경은 제공하지 않는다.
- 같은 제출의 재시도로 신청과 안내 대상이 중복 생성되지 않도록 제출 식별자를 사용한다. 응답 유실 시 원래 입력과 식별자를 함께 보존하고 저장 여부가 확인되기 전에 새 신청으로 자동 전환하지 않는다. 입력 오류·접수 중단은 서버에서 검증하고 익명 POST에도 CSRF를 적용한다.
- Django Q2의 PostgreSQL ORM broker·기본 큐 하나·qcluster 하나를 사용한다. 메일은 건별 작업으로 병렬 처리하고 오래된 대상부터 제한된 batch를 이어 등록한다. 오류별 재시도와 발송 기록으로 중복 실행을 제어하며 초당 제한과 일일 한도 초과의 대기 정책을 구분한다.
- 한국 시간의 연락 가능 날짜에 HTML·일반 텍스트 안내를 생성한다. 공통 Django 이메일 API를 사용하고 환경별 backend 설정으로 개발은 locmem 모의 처리, 운영은 django-ses를 통한 AWS SES 발송으로 구분한다.
- 안내는 pending·시도 횟수 0으로 시작한다. task에서 SES API 접수 응답·MessageId를 함께 기록하고 결과 저장용 signal receiver는 추가하지 않는다. 응답 유실 등 접수 여부가 불명확하면 자동 재발송을 중단하고 확인 필요로 보존한다. 실제 전달·반송 확인은 이번 범위에 포함하지 않으며 정확히 한 번 외부 전달을 보장한다고 표현하지 않는다.
- 이미지 교체·교육 삭제 후 파일 정리를 Q2로 전환한다. DB 변경과 정리 작업 등록의 일관성, rollback·공유 참조·재연결 보호를 유지하고 제한적 재시도 후 Q2 실패 작업으로 관리한다.
- task 이름에서 상담 날짜 안내 이메일과 미참조 교육 이미지 삭제라는 업무 목적을 드러낸다. 긴 task의 보조 처리만 `education/tasks_support/`로 분리하고 기존 스케줄·큐 등록 경로와 테스트·문서를 함께 전환한다. 동작·모델명·DB schema는 변경하지 않는다.
- 기존 문서의 fetch 예정·자동 메일 미정·동기 이미지 정리 설명을 구현 시 갱신한다. main spec의 즉시 정리 시나리오는 작업 처리 후 정리로 변경한다.

범위 제외: 신청 관리 CRUD·관리자 신청 목록·상태 변경 UI/API, 교육 편집 UI, 별도 DLQ, Redis, mail/media 대체 cluster, autoscale, Google Spreadsheet 내보내기, SNS·SQS·웹훅·SES 이벤트 수집과 실제 전달·반송 확인, 실제 AWS 리소스 생성·배포·유료 호출. 신청 관리·내보내기·AWS 배포 구성은 후속 예정으로 유지한다. 추가적인 접수 결과 대조·반송 확인이 필요해질 때 SNS와 django-ses 웹훅을 연동한다.

## Capabilities

### New Capabilities

- `education-applications`: 교육정보 API를 사용하는 모바일 신청 폼, 주소 검색, 검증·접수 저장·반복 제출 보호와 접수 상태 표시.
- `application-notifications`: 날짜별 안내 생성, 환경별 모의/SES 발송, API 접수 결과 기록·동시 실행 제어·선별 재시도·결과 불명 보존.
- `background-processing`: PostgreSQL 기반 Q2 기본 큐, 작업 등록의 transaction 일관성, worker 실행·실패 관리·정상 종료.

### Modified Capabilities

- `education-catalog`: 실제 신청 진입 링크를 제공하고 교육 삭제·이미지 교체 정리를 Q2 작업으로 전환한다. 실행 시 참조 재검사와 실패 이력을 명시한다.

## Impact

- `src/education/`: 신청·안내 모델 및 생성 migration, DRF serializer/API, 날짜별 작업·Django 이메일 발송과 API 접수 결과 기록, 기존 signals·모델 저장 transaction 경계와 관련 테스트. `tasks.py`에는 task 진입점·실행 흐름을 두고 긴 task의 내부 처리는 `tasks_support/`로 분리하며 기존 `notifications.py`는 상담 안내 이메일 전송 지원 모듈에 통합한다.
- `src/config/settings/`, `pyproject.toml`, `uv.lock`, `.env.example`: Q2 공통 설정·dev/prod 이메일 backend 분리, django-ses 운영 의존성·SES 설정과 IAM 기본 credential chain. SNS·웹훅 설정과 events extra는 추가하지 않는다.
- `src/templates/`, `src/static/`, `package.json`, `package-lock.json`: 신청·메일 template, Axios 로컬 자산·화면 JavaScript, Tailwind 생성 CSS. 평가 실행에 프론트 빌드를 요구하지 않는다.
- `README.md`, `docs/architecture.md`, `docs/development.md`, `docs/task-queue-comparison.md`: API 계약·실행·검증·외부 연결·수명주기와 구현 상태를 같은 작업에서 동기화한다.
- 기존 교육·프리셋·이미지 키를 보존하고 DB를 초기화하지 않는다. `.idea/`와 이 change 이전의 문서 변경은 덮어쓰지 않는다.
