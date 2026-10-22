# Proposal

## Why

담당자용 백오피스가 main의 `6abb23f`에 통합됐지만 교육 프리셋만으로는 20건 단위 페이지네이션과 다양한 상담·메일 상태를 확인할 수 없다. 실제 개인정보나 기존 데이터를 초기화하지 않고 평가 환경에 신청 샘플 32건을 선택적으로 추가한다.

## What Changes

- `seed_educations --with-applications --staff-user <기존 사용자명>`으로 교육 3개에 신청을 11·11·10건 추가한다. 옵션 없는 교육·이미지 준비와 운영 S3 초기화 계약은 유지한다.
- 접수 8·상담중 6·재연락 10·완료 4·취소 4건을 재현 가능한 최신순 혼합 목록으로 제공한다. 재연락은 오늘 3·지난 날짜 3·미래 날짜 2·일정 미정 2건이다.
- 최초 생성 시 한국 시각과 `python-dateutil`의 `relativedelta`로 접수·연락 날짜·상담·메일의 상대 시각을 간단히 구성한다. 실제 화면과 기능 확인에 필요한 날짜 관계를 유지하며 가상 이름·주소와 `example.com` 이메일, 상담 없음·복수 상담·부재중·재연락 합의·정정 사례를 포함한다.
- 고정 제출 UUID로 재실행을 식별하고 기존 신청·상담·이력·담당자 수정값은 통째로 보존한다. 신규 DB 저장은 교육을 포함해 실행 단위로 원자적으로 처리한다.
- 샘플 옵션은 개발 설정·모의 모드·locmem 메일 환경에서만 허용한다. 생성 중 메일 발송·큐/스케줄 등록·계정 생성은 하지 않는다. 합성 SES 접수 증거는 만들지 않는다.
- README·운영·검증 문서에 선택 명령, 계정 준비, worker 중지 상태의 화면 확인과 이후 상태 변화, 보존·실패 계약을 동기화한다.

## Capabilities

### New Capabilities

없음. 교육과 신청을 함께 준비하는 기존 초기 데이터 capability를 확장한다.

### Modified Capabilities

- `education-presets`: 기존 교육 초기화에 개발 전용 신청·상담·메일 샘플의 선택 생성, 분포·날짜 정합성, 재실행 보존과 전체 DB 롤백 계약을 추가한다.

## Impact

- 구현 대상은 `src/education/management/commands/seed_educations.py`와 `presets/education/`의 신청 샘플 정의다. 필요한 전용 로더는 이 명령의 내부 책임으로 한정한다.
- `EducationApplication.save()`의 원본 snapshot·history, `ConsultationRecord.save()`의 누적·정정 검증과 기존 안내·시도 모델을 사용한다. 공개 API·관리 저장 서비스·권한·worker 정책을 변경하지 않는다.
- `test_presets.py`·`test_backoffice.py`를 확장하고 PostgreSQL 테스트 DB·임시 미디어·격리 브라우저 환경에서 검증한다. 기존 141개 통과 기록은 기준선이며 이번 change의 검증 결과로 간주하지 않는다.
- `python-dateutil`은 기존 lockfile의 간접 의존성을 직접 의존성으로 명시해 재사용하며 이 목적만으로 버전을 올리지 않는다. 그 밖의 새 패키지·모델 필드·migration·범용 프리셋 엔진·계정/비밀번호 자동 생성·초기화/삭제 옵션·실제 SES 발송은 제외한다. 실제 SES 접수 화면의 증거 검증은 기존 테스트와 별도 opt-in 운영 검증 범위로 남긴다.
- 이번 단계는 계획 artifact 작성만 수행한다. 구현과 실제 개발 DB 샘플 생성, commit·push는 수행하지 않는다.
