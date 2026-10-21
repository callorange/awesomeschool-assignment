# Design

## Context

동기는 proposal.md의 Why를 따른다. 현재 Education은 JSONField로 목표·추천대상·시수별 커리큘럼을 보관한다. 구조 검증은 seed_educations.py의 private 함수에 있고, 명령은 full_clean() 후 별도 검증을 수행한다. 일반 모델 검증은 같은 구조 계약을 보장하지 않는다.

프리셋 명령은 누락 교육만 생성하고 기존 교육·이미지를 보존한다. 상세는 모든 교육을 공개하며 신청 경로는 없다. admin.py는 교육을 등록하지 않는다. 현재 초기 교육 3개는 코치 출강 교육이며 기존 모델 테스트는 구조가 불완전한 JSON을 직접 save하는 경우가 있다.

위 내용은 최초 계획 당시의 기준이다. 운영 정보·공통 검증 범위는 이미 구현·검증했으며, 이번 보완은 아래 이미지 정책을 추가하는 계획이다. 현재 프리셋 키는 education/presets/<slug>-<sha256>.png이고 일반 FileField의 upload_to는 education/이다. 로컬 기본 Storage와 S3 file_overwrite=False가 덮어쓰기를 방지하지만 교육 삭제·교체 후 파일 정리는 없다. 현재 프리셋 테스트에는 서로 다른 교육이 같은 이미지 키를 공유하는 사례가 있다.

## Goals / Non-Goals

**Goals:**
- 운영 방식과 접수 상태는 명시적 값으로 구분하고, 협의할 운영 조건은 안내 텍스트로 제공한다.
- 모델 검증과 프리셋 검증의 규칙 원본을 일원화하되 기존 JSON·공개 URL·초기화 보존 계약을 유지한다.
- migration 기본값과 프리셋 신규 생성값을 구분하여 기존 콘텐츠를 덮어쓰지 않는다.
- 신규 이미지는 교육별로 배치하고, DB commit 이후 미참조인 이전 파일만 정리한다. 기존 저장 키와 프리셋 실패 복구 계약은 유지한다.

**Non-Goals:**
- save()·QuerySet.update()·bulk_create()를 포함한 모든 ORM 쓰기를 검증하는 체계는 만들지 않는다.
- 모델 JSON을 다회·교시 범위·반 편성용 범용 schema로 확장하거나 신청·편집 기능을 미리 구현하지 않는다.
- 기존 이미지 일괄 이동, 저장소 전수 청소, 파일 정리 작업 큐·주기 작업·완전한 고아 파일 방지는 구현하지 않는다.

## Decisions

### 1. Education에 세 필드만 추가

| 필드 | 형태 | 기본값·정책 |
| --- | --- | --- |
| operation_type | CharField(max_length=20), TextChoices | instructor_led(코치 출강); 다른 값은 courseware(코스웨어) |
| operation_note | TextField(blank=True) | 빈 문자열; 일반 텍스트 |
| is_accepting_inquiries | BooleanField | true |

기존 필드와 JSON 구조는 유지한다. 별도 Option·Offering 모델은 실제 구성 선택이나 회차 등록이 없으므로 도입하지 않는다. 지역·일정·인원은 상담에서 협의하는 안내이며 자동 신청 제한으로 해석하지 않는다. 접수 여부와 공개 여부는 다르므로 비활성 교육도 목록·상세에서 조회한다.

기존 레코드에는 위 기본값을 적용한다. 기존 교육을 프리셋 값으로 갱신하는 RunPython은 넣지 않는다. 신규 프리셋은 운영 방식·접수 여부를 명시하고, 일정·진행 조건은 상담 후 협의한다는 과제용 안내를 넣는다. 실제 날짜·가격·정원·전국 가능 등을 추정하지 않는다. 수집 기록 4개 필드는 프리셋 JSON에만 남기고 모델 저장·상세 렌더링에서는 제외한다. JSON의 editorial_note에서 원본 요약과 과제 운영 안내를 구별한다.

### 2. JSONField validator를 모델 검증과 프리셋에서 재사용

education/validators.py에 migration에서 참조 가능한 module-level validator를 둔다. goals·audiences는 동일한 문자열 목록 validator를, curriculum은 기존 구조 validator를 사용한다. Django ValidationError로 오류를 보고하고 각 JSONField의 validators에 연결하여 full_clean()에서 필드별 오류를 제공한다.

기존 규칙인 비어 있지 않은 문자열 목록, 양의 정수 시수의 유일성, 교시 수 일치, 연속 교시 번호, 필수 설명을 유지한다. boolean은 정수 시수·교시 번호로 허용하지 않는다. 객체·목록 여부와 키를 검사해 KeyError·TypeError를 사용자에게 유출하지 않는다. 새로운 임의 길이 제한이나 금칙어 규칙은 추가하지 않는다.

초기화 명령은 기존 full_clean(validate_unique=False)로 모델 검증을 재사용하고 중복 private 콘텐츠 검사만 제거한다. 이미지 경로·PNG·중복 slug 검사, 사전 검증 후 저장, transaction·파일 재사용은 명령에 남긴다. 모델 clean()에 한꺼번에 몰거나 명령 private 함수를 모델에서 가져오는 대안보다 필드 validator가 책임과 오류 위치를 명확히 한다.

save()는 override하지 않는다. 직접 save로 무효 JSON을 저장할 수 있는 기존 ORM 특성을 변경하지 않고 full_clean()이 검증 경계임을 문서화한다. 향후 ModelForm은 모델 검증을 활용하고 DRF 입력 경로는 별도로 같은 계약에 연결해야 한다. 검증 테스트는 정상 프리셋 형태로 full_clean()을 호출하며 DB 영속화·고유성 테스트는 실제 DB를 유지한다.

### 3. 상세에 읽기 전용 운영 정보 제공

기존 상세 template에 get_operation_type_display와 operation_note, 상담 접수 가능·중단 상태를 표시한다. 안내가 비어 있으면 안내 블록을 생략하고 텍스트는 기본 escaping으로 출력한다. 접수 가능 상태도 수강 확정을 뜻하지 않으며 실제 신청 링크를 추가하지 않는다. views의 전체 교육 조회와 URL은 유지한다. 두 운영 방식과 true/false 상태를 데이터 변경으로 렌더링 테스트한다.

### 4. 개인정보·권한 경계 유지

새 정보는 공개 교육 운영 정보이며 신청자 개인정보를 담지 않는다. admin 등록·인증·권한·신청 POST 경로는 추가하지 않는다. 접수 활성 값은 후속 신청 API가 서버에서 검증할 계약이며 이번에는 안내와 저장만 보장한다.

### 5. 교육별 이미지 경로와 파일명

공통 경로 모듈을 두고 신규 저장 키를 education/<media_id.hex>/images/<generated-name>.<extension>으로 구성한다. Education.media_id는 default=uuid.uuid7, unique=True, editable=False인 UUIDField로 DB 저장 전에 생성하며 교육 생성 후 변경하지 않는다. 기존 숫자 PK는 유지하고 slug 변경과 이미지 교체 후에도 같은 교육 폴더를 사용한다. UUIDv7은 Python 3.14 표준 라이브러리를 사용하고 디렉터리는 하이픈 없는 32자 hex로 표현한다. Python의 default=uuid7만 사용하며 DB 기본값은 두지 않는다.

- 프리셋은 교육별 고정 UUIDv7 media_id를 JSON에 기록하고 내용의 SHA256과 .png를 사용한다. UUID의 유효성·버전·중복을 사전 검사한다. 같은 입력에서 키가 같아야 실패 후 재실행에서 파일을 재사용할 수 있다.
- FileField의 일반 파일 저장은 module-level upload_to callable에서 uuid4().hex와 파일 확장자를 사용한다. 원본 basename은 키에 사용하지 않는다. 프리셋에서 이미 저장한 상대 키를 문자열로 지정하는 경로에는 UUID를 다시 붙이지 않는다.
- 로컬·S3의 덮어쓰기 금지를 유지하고 실제 Storage.save() 반환 키를 기록한다. UUID만으로 덮어쓰기 방지를 보장한다고 가정하지 않는다.
- 기존 education/presets/ 또는 education/ 키는 그대로 제공한다. 신규 저장에만 규칙을 적용하므로 데이터 이동 migration과 자동 파일 이동은 없다. 향후 파일 교체 시에는 새 키로 저장하고 이전 키를 정리한다.

날짜별 계층과 해시 prefix 분산은 현재 규모에 필요하지 않다. 프리셋까지 UUID로 바꾸면 실패 파일 재사용을 잃으므로 두 파일명 정책의 차이를 유지한다. 이미지 업로드 폼·API·별도 이미지 모델·파일 형식 정책 확대는 이번 보완에 포함하지 않는다.

### 6. commit 이후 삭제·교체 파일 정리

작은 signal 처리로 모델 delete()와 QuerySet.delete()에 대응하고, 일반 save()를 통한 이미지 교체를 처리한다. 앱 ready()에서 signal을 등록한다. 기존 save() 자동 입력 검증을 도입하지 않는 결정은 유지한다.

- post_delete에서 삭제된 교육의 파일 키와 Storage를 수집한다.
- 교체는 pre_save에서 같은 DB alias의 기존 이미지 키를 읽고 post_save에서 실제 저장된 키와 비교한다. 신규 생성·같은 키·update_fields에서 image를 제외한 저장은 교체 정리 대상이 아니다. 파일 내용이 저장된 뒤 Storage가 반환한 키를 기준으로 판단한다.
- transaction.on_commit()에 Storage·이전 키·DB alias를 값으로 캡처한 정리 callback을 등록한다. callback 실행 시 같은 alias의 Education.image 참조를 다시 조회하고 참조가 없을 때만 Storage.delete()를 호출한다. 같은 transaction에서 파일을 다시 연결한 경우도 보존한다.
- 파일 삭제는 Storage API로 수행한다. 로컬 절대 경로나 S3 SDK를 직접 사용하지 않고, 기존 경로와 새 경로 모두 같은 정책을 적용한다. DB 정리가 실패·rollback되면 callback이 실행되지 않으므로 이전 파일은 남는다.
- 정리 오류는 대상 저장 키와 예외를 credential 없이 기록하고 다른 callback을 막지 않게 처리한다. 파일 삭제 실패가 DB rollback을 의미하지 않으며 자동 재시도 큐는 두지 않는다.

QuerySet.update()·bulk_update()·직접 SQL로 image 키를 바꾸는 경로는 signal을 우회하므로 수명주기 계약에 포함하지 않는다. 향후 편집·API는 일반 모델 저장 경로를 사용해야 한다. 교육 이미지의 공유 참조는 현재 소유 모델인 Education 내에서 확인하며 범용 자산 참조 테이블을 추가하지 않는다.

정상 삭제 정리와 저장 실패 잔여 파일은 별개다. 새 이미지가 저장된 뒤 DB 쓰기가 rollback되거나 프로세스가 중단되면 새 파일이 남을 수 있다. 프리셋 명령은 종전대로 잔여 파일을 알리고 재실행에서 재사용한다. DB rollback 시 저장소 전체를 정리하거나 presets/education/images 원본을 삭제하지 않는다. 기존 test_partial_database_reuses_existing_image는 commit 이후 파일이 정리된 경우 재생성하고, 파일이 실제로 남은 경우 재사용하는 계약으로 구분해 보완한다.

## Risks / Trade-offs

- [직접 ORM 쓰기는 검증을 우회할 수 있음] → full_clean() 경계를 명시하고 실제 입력 경로인 초기화 명령에서 호출한다. 미래 입력 경로는 그 구현 시 연결한다.
- [기존 임의 교육에 코치 출강 기본값이 부적합할 수 있음] → 이번 기본값은 현재 제공하는 교육 3개에 근거한 가정이다. 다른 운영 교육을 별도로 넣은 환경은 배포 전 확인하며 제목 기반 자동 추론은 하지 않는다.
- [기존 데이터의 진행 안내가 빈 값으로 남음] → 정상 상태로 허용하고 신규 프리셋과 구별한다. 재초기화로 사용자 데이터를 덮어쓰지 않는다.
- [기존 JSON은 다회·교시 범위 전체를 표현하지 못함] → 현재 교육 3개의 계약을 유지한다. 실제 지원 대상 확대 시 별도 변경으로 다룬다.
- [출강·코스웨어와 접수 상태의 새 안내가 작은 화면에서 늘어남] → 기존 레이아웃을 사용하고 360·768·1280px에서 확인한다.
- [Storage 쓰기·삭제는 DB와 원자적으로 commit되지 않음] → 기존 파일은 commit 이후 정리하고 삭제 실패를 기록한다. rollback 새 파일·callback 실행 전 중단으로 생기는 잔존 파일은 전수 청소 범위를 추가하지 않고 한계로 명시한다.
- [같은 파일의 공유 참조를 지울 위험] → callback 시 참조를 다시 조회한다. UUID 신규 키와 기존 키를 함부로 재연결하지 않는 저장 경로를 사용하며, 범용 동시 자산 재연결 제어는 도입하지 않는다.
- [운영 모드 정리가 S3 삭제를 수반함] → 로컬 임시 Storage와 실제 테스트 DB로 검증하고 S3 URL·설정은 외부 호출 없이 확인한다. 실제 운영 파일 삭제는 개발 검증에서 수행하지 않는다.

## Migration Plan

1. 사용자 요청으로 0001_initial은 유지하고 로컬 개발 중 생성한 0002~0006은 삭제한다. 모델의 최종 상태를 기준으로 Django makemigrations education --name improve_education_model --noinput으로 0002를 생성한다. 생성 후 import·서식만 Ruff로 정리하고 migration 코드는 직접 작성하거나 수정하지 않는다.
2. source_url·source_image_url·collected_on·editorial_note는 제거하고 운영 정보·UUIDv7·표시명·validator·upload_to 상태를 한 migration에 포함한다. media_id는 Python default=uuid7만 사용한다.
3. 이 프로젝트의 Compose DB 컨테이너와 postgres_data 볼륨만 사용자 승인으로 삭제한 뒤 다시 시작한다. 프리셋 JSON·이미지 원본·로컬 media 파일은 유지한다. 빈 DB에서 0001 → 0002 적용 후 프리셋을 설정한다.
4. 새 0002는 기존 데이터 업그레이드나 구·신 코드 동시 실행을 지원하는 migration이 아니다. 고유 UUID callable 기본값과 수집 기록 열 삭제가 있으므로 이전 이력을 적용한 DB의 보존·역적용 호환성을 주장하지 않는다. 수동 lock_timeout·RunSQL·backfill은 추가하지 않는다.
5. 실제 PostgreSQL 빈 DB 적용과 프리셋 3개 생성, UUID·파일 내용·JSON 메타데이터 제외, 재실행 무변경을 검증한다. 격리 테스트도 0001의 빈 테이블에서 최신 schema로 전환하는 계약을 검증한다.
