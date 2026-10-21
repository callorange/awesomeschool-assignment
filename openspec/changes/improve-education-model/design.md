# Design

## Context

동기는 proposal.md의 Why를 따른다. 현재 Education은 JSONField로 목표·추천대상·시수별 커리큘럼을 보관한다. 구조 검증은 seed_educations.py의 private 함수에 있고, 명령은 full_clean() 후 별도 검증을 수행한다. 일반 모델 검증은 같은 구조 계약을 보장하지 않는다.

프리셋 명령은 누락 교육만 생성하고 기존 교육·이미지를 보존한다. 상세는 모든 교육을 공개하며 신청 경로는 없다. admin.py는 교육을 등록하지 않는다. 현재 초기 교육 3개는 코치 출강 교육이며 기존 모델 테스트는 구조가 불완전한 JSON을 직접 save하는 경우가 있다.

## Goals / Non-Goals

**Goals:**
- 운영 방식과 접수 상태는 명시적 값으로 구분하고, 협의할 운영 조건은 안내 텍스트로 제공한다.
- 모델 검증과 프리셋 검증의 규칙 원본을 일원화하되 기존 JSON·공개 URL·초기화 보존 계약을 유지한다.
- migration 기본값과 프리셋 신규 생성값을 구분하여 기존 콘텐츠를 덮어쓰지 않는다.

**Non-Goals:**
- save()·QuerySet.update()·bulk_create()를 포함한 모든 ORM 쓰기를 검증하는 체계는 만들지 않는다.
- 모델 JSON을 다회·교시 범위·반 편성용 범용 schema로 확장하거나 신청·편집 기능을 미리 구현하지 않는다.

## Decisions

### 1. Education에 세 필드만 추가

| 필드 | 형태 | 기본값·정책 |
| --- | --- | --- |
| operation_type | CharField(max_length=20), TextChoices | instructor_led(코치 출강); 다른 값은 courseware(코스웨어) |
| operation_note | TextField(blank=True) | 빈 문자열; 일반 텍스트 |
| is_accepting_inquiries | BooleanField | true |

기존 필드와 JSON 구조는 유지한다. 별도 Option·Offering 모델은 실제 구성 선택이나 회차 등록이 없으므로 도입하지 않는다. 지역·일정·인원은 상담에서 협의하는 안내이며 자동 신청 제한으로 해석하지 않는다. 접수 여부와 공개 여부는 다르므로 비활성 교육도 목록·상세에서 조회한다.

기존 레코드에는 위 기본값을 적용한다. 기존 교육을 프리셋 값으로 갱신하는 RunPython은 넣지 않는다. 신규 프리셋은 운영 방식·접수 여부를 명시하고, 일정·진행 조건은 상담 후 협의한다는 과제용 안내를 넣는다. 실제 날짜·가격·정원·전국 가능 등을 추정하지 않는다. 기존 수집일은 새 안내를 작성한 날짜로 바꾸지 않고 editorial_note에서 원본 요약과 과제 운영 안내를 구별한다.

### 2. JSONField validator를 모델 검증과 프리셋에서 재사용

education/validators.py에 migration에서 참조 가능한 module-level validator를 둔다. goals·audiences는 동일한 문자열 목록 validator를, curriculum은 기존 구조 validator를 사용한다. Django ValidationError로 오류를 보고하고 각 JSONField의 validators에 연결하여 full_clean()에서 필드별 오류를 제공한다.

기존 규칙인 비어 있지 않은 문자열 목록, 양의 정수 시수의 유일성, 교시 수 일치, 연속 교시 번호, 필수 설명을 유지한다. boolean은 정수 시수·교시 번호로 허용하지 않는다. 객체·목록 여부와 키를 검사해 KeyError·TypeError를 사용자에게 유출하지 않는다. 새로운 임의 길이 제한이나 금칙어 규칙은 추가하지 않는다.

초기화 명령은 기존 full_clean(validate_unique=False)로 모델 검증을 재사용하고 중복 private 콘텐츠 검사만 제거한다. 이미지 경로·PNG·중복 slug 검사, 사전 검증 후 저장, transaction·파일 재사용은 명령에 남긴다. 모델 clean()에 한꺼번에 몰거나 명령 private 함수를 모델에서 가져오는 대안보다 필드 validator가 책임과 오류 위치를 명확히 한다.

save()는 override하지 않는다. 직접 save로 무효 JSON을 저장할 수 있는 기존 ORM 특성을 변경하지 않고 full_clean()이 검증 경계임을 문서화한다. 향후 ModelForm은 모델 검증을 활용하고 DRF 입력 경로는 별도로 같은 계약에 연결해야 한다. 검증 테스트는 정상 프리셋 형태로 full_clean()을 호출하며 DB 영속화·고유성 테스트는 실제 DB를 유지한다.

### 3. 상세에 읽기 전용 운영 정보 제공

기존 상세 template에 get_operation_type_display와 operation_note, 상담 접수 가능·중단 상태를 표시한다. 안내가 비어 있으면 안내 블록을 생략하고 텍스트는 기본 escaping으로 출력한다. 접수 가능 상태도 수강 확정을 뜻하지 않으며 실제 신청 링크를 추가하지 않는다. views의 전체 교육 조회와 URL은 유지한다. 두 운영 방식과 true/false 상태를 데이터 변경으로 렌더링 테스트한다.

### 4. 개인정보·권한 경계 유지

새 정보는 공개 교육 운영 정보이며 신청자 개인정보를 담지 않는다. admin 등록·인증·권한·신청 POST 경로는 추가하지 않는다. 접수 활성 값은 후속 신청 API가 서버에서 검증할 계약이며 이번에는 안내와 저장만 보장한다.

## Risks / Trade-offs

- [직접 ORM 쓰기는 검증을 우회할 수 있음] → full_clean() 경계를 명시하고 실제 입력 경로인 초기화 명령에서 호출한다. 미래 입력 경로는 그 구현 시 연결한다.
- [기존 임의 교육에 코치 출강 기본값이 부적합할 수 있음] → 이번 기본값은 현재 제공하는 교육 3개에 근거한 가정이다. 다른 운영 교육을 별도로 넣은 환경은 배포 전 확인하며 제목 기반 자동 추론은 하지 않는다.
- [기존 데이터의 진행 안내가 빈 값으로 남음] → 정상 상태로 허용하고 신규 프리셋과 구별한다. 재초기화로 사용자 데이터를 덮어쓰지 않는다.
- [기존 JSON은 다회·교시 범위 전체를 표현하지 못함] → 현재 교육 3개의 계약을 유지한다. 실제 지원 대상 확대 시 별도 변경으로 다룬다.
- [출강·코스웨어와 접수 상태의 새 안내가 작은 화면에서 늘어남] → 기존 레이아웃을 사용하고 360·768·1280px에서 확인한다.

## Migration Plan

1. 기존 migration을 수정하지 않고 세 필드와 JSONField validator 상태를 반영한 새 migration을 생성한다. 일반적인 소규모 개발 과제 DB의 schema 변경이며 무중단 배포를 주장하지 않는다.
2. sqlmigrate로 기존 열·콘텐츠를 갱신하거나 삭제하지 않는지 확인한다. 실제 PostgreSQL 격리 테스트에서 직전 schema에 생성한 정상 교육의 PK·JSON·이미지·출처·순서를 전환 후 비교하고 새 기본값을 확인한다. MigrationExecutor를 사용하면 종료 시 최신 schema를 복원한다.
3. 신규 초기화·재실행 보존·오류 시 무부작용과 기존 파일 롤백·재사용 테스트를 실행한다. 개발 DB를 초기화하거나 운영 저장소에 업로드해 검증하지 않는다.
4. 배포 시 migration 후 새 코드를 사용한다. 앱 롤백은 기존 열을 유지하는 방향을 우선한다. 역 migration은 새 필드 값을 잃으므로 필요하면 별도로 보존한 뒤 명시적으로 수행한다.
