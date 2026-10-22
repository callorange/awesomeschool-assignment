# Proposal

## Why

현재 신청·상담 관리는 Django admin에서만 제공되어 담당자가 핵심 업무 흐름을 한눈에 확인하기 어렵다. 제출 검토자가 기존 admin과 비교할 수 있도록 별도 주소에 신청 관리 중심의 백오피스를 제공한다.

## What Changes

- `/backoffice/`에 관리자 로그인·로그아웃, 신청 목록, 신청 상세·수정 화면을 추가한다. `/admin/`은 유지하고 백오피스에서 이동 링크를 제공한다.
- 공개 백오피스 레이아웃을 참고해 기존 Tailwind CSS로 반응형 화면을 구성한다. desktop 사이드바·상단바·본문과 모바일 접이식 메뉴를 공통 template로 분리하여 향후 메뉴와 업무 화면을 추가하기 쉽게 한다.
- 기존 Django 계정·세션과 모델별 권한을 공유한다. 신청 조회·정정·상태·재연락 일정·상담 조회와 추가를 지원한다.
- 신청 상세에서 권한에 따라 이메일 처리 상태·예정/처리 시각·시도 횟수·안전한 오류 코드를 조회한다. 개발 모의 완료와 SES 접수, 실제 전달 여부를 구분한다.
- 로그인·로그아웃·신청 저장은 일반 POST, 목록·상세 이동과 검색·필터·페이지 이동은 일반 GET으로 처리한다. 이메일 상태 새로고침만 Ajax GET으로 부분 갱신하여 작성 중인 신청·상담 입력을 유지한다.
- 기존 신청 저장 서비스·검증·변경 이력·상담 보존·메일 경합 제어를 재사용하며 신청과 새 상담의 저장은 원자적으로 처리한다.
- 권한에 따라 읽기 전용·변경사항 저장·상담 추가를 구분한다. 신청과 상담을 함께 저장할 때는 기본 해제된 '상담 기록도 추가'를 명시적으로 선택하며, 상담 추가가 요청되면 결과·내용을 필수 검증한다.
- 이번 범위에서 task 관리, 재발송, Spreadsheet 내보내기, 신청 수동 생성·삭제, 교육 편집, 계정 관리, 통계 대시보드, 이력 상세 화면은 제외한다.
- 후속 후보는 Spreadsheet 내보내기 등이며 이번 제출의 구현·완료 조건에 포함하지 않는다.

## Capabilities

### New Capabilities

- `application-backoffice`: Django admin과 공존하는 담당자용 인증·권한 기반 신청/상담 관리와 이메일 상태 조회 화면.

### Modified Capabilities

없음. `application-management`의 기본 admin 계약과 `application-notifications`의 처리 정책은 유지하며 새 UI에 동일한 불변조건을 적용한다.

## Impact

- `src/config/urls.py`, `src/education/`의 백오피스 URL·view·form 및 `src/templates/backoffice/`가 구현 대상이다. 기존 `forms/application.py`, `forms/consultation.py`, `services/applications.py`의 계약을 재사용한다.
- 기존 Tailwind·Axios를 사용하고 백오피스 상세 전용 JavaScript 진입점과 이메일 상태 부분 조회 경로를 추가하여 CSS·JS를 재빌드한다. 새 패키지·SPA·관리자 REST API·DB schema 변경은 계획하지 않는다.
- 로그인·모델별 접근 통제와 실제 PostgreSQL 저장·rollback 테스트, 브라우저 반응형 확인 및 `/admin/` 회귀 확인이 필요하다.
- README와 기능 검증·운영·아키텍처 문서의 관련 부분에 두 진입점, 공유 세션과 권한, 구현 범위를 동기화한다.
