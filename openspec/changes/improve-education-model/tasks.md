# Tasks

## 1. 교육 모델과 공통 검증

- [ ] 1.1 Education에 운영 방식 TextChoices·operation_type·operation_note·is_accepting_inquiries를 추가하고 정상 값의 영속화·기본값·잘못된 운영 방식의 full_clean() 오류를 모델 테스트로 확인한다.
- [ ] 1.2 기존 문자열 목록·커리큘럼 검증을 module-level JSONField validator로 옮긴다. 정상 프리셋, 빈 목록·공백·잘못된 타입·누락 키·중복/boolean 시수·교시 수와 순서 오류를 full_clean()에서 필드별 ValidationError로 확인하며 save() 자동 검증은 추가하지 않는다.
- [ ] 1.3 새 migration을 생성하고 기존 migration은 유지한다. sqlmigrate로 SQL을 확인하고 격리된 PostgreSQL migration 테스트에서 기존 PK·콘텐츠·미디어·출처·정렬 보존 및 새 기본값을 검증한다. uv run python src/manage.py test education.tests.test_models와 새 migration 테스트를 실행한다.
- [ ] 1.4 docs/architecture.md에 세 필드·JSON 검증 경계·직접 ORM 쓰기의 한계를 반영하고 모델 docstring과 실제 계약의 일치를 확인한다.

## 2. 프리셋과 초기화 계약

- [ ] 2.1 프리셋 3개에 코치 출강·접수 활성·상담 후 일정과 조건을 협의한다는 안내를 명시하고 editorial_note로 과제용 안내를 구별한다. 기존 이미지·커리큘럼·출처와 수집일이 유지되는지 확인하고 신규 설정값을 프리셋 테스트로 검증한다.
- [ ] 2.2 seed_educations의 full_clean(validate_unique=False)에서 공통 콘텐츠 검증을 사용하고 중복 private 검사를 제거한다. 이미지 사전 검사·DB transaction·파일 재사용은 유지하고 잘못된 운영 방식과 콘텐츠가 DB·미디어 쓰기 전에 거부되는지 테스트한다.
- [ ] 2.3 수정한 운영 방식·진행 안내·접수 상태의 재실행 보존을 테스트하고 기존 저장 실패·롤백·파일 재사용 테스트를 유지한다. uv run python src/manage.py test education.tests.test_presets를 실행하고 README의 초기 데이터 설명과 기존 데이터 보존 정책을 동기화한다.

## 3. 공개 운영 안내

- [ ] 3.1 상세 template에 운영 방식·선택적 진행 안내·접수 가능/중단 안내를 표시한다. 두 운영 방식·빈 안내·HTML escaping·접수 중단 시 랜딩/상세 접근 유지·가짜 신청 링크 부재를 페이지 테스트로 검증한다. uv run python src/manage.py test education.tests.test_pages를 실행한다.
- [ ] 3.2 npm run build:css로 template 변경에 필요한 생성 CSS를 반영하고 360·768·1280px에서 운영 안내의 줄바꿈·잘림·기존 커리큘럼과 탐색을 확인한다. 같은 입력의 재빌드 hash 일치와 CSS·이미지 HTTP 200을 확인한다.
- [ ] 3.3 README의 구현 상태·교육 신청을 상담 접수로 해석한 설계 의도·향후 신청 기능의 서버 접수 상태 검사 책임을 동기화한다. 신청·편집 기능이 구현된 것으로 서술하지 않았는지 코드와 비교한다.

## 4. 통합 검증

- [ ] 4.1 로컬 DB 환경에서 uv run python src/manage.py check, uv run python src/manage.py makemigrations --check --dry-run, uv run python src/manage.py test education, uv run ruff check ., uv run ruff format --check .를 실행한다. 실패는 회귀·기존 실패·명령 오류·환경 문제로 구분하고 미검증 범위를 기록한다.
- [ ] 4.2 최종 diff에서 기존 공개 URL·JSON 형태·미디어 참조 보존, 신규 모델/신청 경로/외부 연결 부재와 문서 정합성을 확인하고 OpenSpec validate --strict 통과를 확인한다.
