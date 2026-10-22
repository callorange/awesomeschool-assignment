# Design

## Context

동기는 [proposal.md](proposal.md)의 Why를 따른다. 현재 `/admin/`과 공개 교육 URL만 있으며 `EducationApplicationForm`은 공통 변경 검증을, `save_application`은 안내→신청 잠금·변경 이력·안내 조정을 수행한다. `ConsultationRecord.save()`는 검증을 포함하고 기존 기록의 수정·삭제를 금지한다. 기본 admin은 POST의 폼 조회 전부터 같은 잠금 순서를 적용한다.

기존 `application-management`는 기본 admin을 대상으로 하므로 수정하지 않는다. 별도 화면 계약은 `specs/application-backoffice/spec.md`에 추가하고 메일 처리 정책은 기존 `application-notifications`를 그대로 적용한다. DB·의존성 변경 없이 제출 전 검증 가능한 크기로 제한한다.

## Goals / Non-Goals

**Goals:**
- 새 UI에서도 기존 모델 권한·보존 규칙·저장 transaction을 유지한다.
- 별도 프론트 서버 없이 기존 Templates·Tailwind와 일반 GET/POST로 업무 흐름을 제공하고 이메일 상태 조회만 Ajax로 부분 갱신한다.
- 기존 admin과 같은 데이터를 편집하고 서로의 변경을 다음 조회에 확인할 수 있게 한다.

**Non-Goals:**
- 인증 저장소, 관리자 REST API, 별도 권한 체계, 낙관적 동시 편집 감지나 신규 발송 동작을 도입하지 않는다.
- 기존 admin의 교육·사용자·이력 상세·내부 task 관리 기능을 복제하지 않는다.

## Decisions

### 1. 기존 앱 안에 백오피스 URL과 view를 분리한다

`src/education/backoffice_urls.py`와 `src/education/backoffice.py`를 두고 `src/config/urls.py`에서 `/backoffice/`에 include한다. template는 `src/templates/backoffice/`에 전용 base·로그인·목록·상세로 배치한다. `/backoffice/`는 신청 목록으로 이동하고 나머지는 `/backoffice/login/`, `/backoffice/logout/`, `/backoffice/applications/`, `/backoffice/applications/<int:pk>/`로 구성한다. 별도 앱·SPA·API 대신 기존 업무 모델과 서비스를 직접 사용해 관리 경계를 늘리지 않는다.

### 2. 계정·세션 공유와 모델별 인가를 별개로 검사한다

Django 기본 LoginView·LogoutView와 관리자용 AuthenticationForm을 재사용하고 활성 staff만 업무 view에 접근시킨다. 미로그인의 업무 페이지 GET은 전용 로그인으로 이동하고 인증됐지만 staff가 아니거나 작업 권한이 없으면 403으로 처리한다. 미인증 상태의 업무 저장 POST와 CSRF 실패는 저장 없이 403 안내로 종료하며 로그인 redirect로 저장을 재개하지 않는다. 안전한 `next`와 POST/CSRF 로그아웃은 기본 인증 view 동작을 사용한다. 계정은 기존 `createsuperuser` 또는 admin에서 준비한다.

목록·상세에는 `view_educationapplication`, 정정에는 추가로 `change_educationapplication`을 요구한다. 상담 열람은 `view_consultationrecord`, 추가는 `add_consultationrecord`, 이메일 영역은 `view_educationapplicationreminderemail`을 따로 검사한다. 부모 신청 조회는 항상 선행한다. 화면 숨김만으로 보호하지 않고 POST 작업 권한도 검사한다. 상담 추가만 가능한 담당자는 신청 입력을 변경하지 않는 상담 추가 작업을 사용한다. 상담 조회 권한이 없으면 정정 대상 목록과 과거 내용을 제공하지 않으며 정정 결과·원기록을 지정한 직접 POST도 거부하고 일반 상담 추가만 허용한다.

같은 사이트의 기본 세션을 유지하므로 어느 관리자 화면에서든 로그인 상태를 공유하고 로그아웃도 함께 적용된다. 별도 인증·세션 분리는 채택하지 않는다.

### 3. 목록은 snapshot을 기준으로 검색·필터링한다

최신 생성 시각·PK 순으로 정렬하고 Django Paginator로 페이지당 20건을 표시한다. 이름·이메일 부분 검색, 신청 당시 교육명·상태·재연락 대상 필터를 GET query로 전달하고 페이지 링크에 유지한다. 교육 선택지는 현재 Education이 아닌 신청의 교육명 snapshot에서 얻어 원본 삭제 신청도 찾을 수 있게 한다. 재연락 today/overdue/undated는 기존 FollowUpFilter와 같은 한국 시각 의미를 유지하되 admin 클래스에 의존하지 않는다. 빈 결과·잘못된 페이지는 paginator의 안전한 페이지 처리로 표시한다.

### 4. 기존 폼과 저장 서비스를 사용하되 POST 전체를 같은 transaction으로 묶는다

신청 정정은 기존 `EducationApplicationForm`을 사용한다. 상담 입력은 백오피스용 `forms/backoffice.py`에서 기존 `ConsultationForm`을 필요한 범위로 조정한다. 부모 신청·작성자·작성 시각·일정은 제출값을 신뢰하지 않고 서버에서 지정한다. 정정 대상 queryset은 현재 신청과 상담 조회 권한으로 제한하고 모델의 검증도 유지한다.

부모 신청 조회 권한을 전제로 저장 UI를 아래와 같이 구성한다. 상담 조회 권한은 상담 내용의 열람·정정에 별도로 적용한다.

| 신청 변경 | 상담 추가 | 화면과 저장 의도 |
| --- | --- | --- |
| 불가 | 불가 | 신청 읽기 전용, 저장 버튼 없음 |
| 가능 | 불가 | 신청 수정 폼과 '변경사항 저장' |
| 불가 | 가능 | 신청 읽기 전용과 필수 상담 폼, '상담 추가' |
| 가능 | 가능 | 신청 수정 폼과 기본 해제된 '상담 기록도 추가', '변경사항 저장' |

POST는 `action=save_application`과 `action=add_consultation`을 구분하고 미지정·알 수 없는 작업은 400으로 거부한다. 작업별 서버 권한 검사는 제출 필드 처리 전에 수행한다. `save_application`에는 신청 변경 권한이 필요하며 `include_consultation`을 선택한 경우 상담 추가 권한도 필요하다. 선택하지 않았으면 상담 폼을 검증·저장하지 않으며 제출에 상담 필드가 남아 있어도 상담을 생성하지 않는다. 선택하면 입력 영역을 펼치고 결과·내용을 필수 검증한다. '상담 추가' 요청은 체크박스 없이 항상 필수 상담 검증을 하며 신청 필드를 저장하지 않는다. 상담 결과 초기값은 선택 안 함으로 두고 선택 여부·오류·입력은 일반 유효성 오류 후에도 유지한다. 영역 펼치기는 native HTML/CSS로 처리하여 JavaScript 없이도 선택과 저장이 가능하게 한다.

쓰기 권한 확인 후 `transaction.atomic()` 안에서 안내→신청 순서로 잠그고 최신 인스턴스로 해당 작업의 폼을 생성·검증한다. 통합 저장은 신청 폼과 명시적으로 선택한 상담 폼이 모두 유효할 때 `save_application`으로 신청을 저장하고 반환된 일정과 현재 사용자를 상담에 기록한다. 상담 추가 전용 작업은 신청 폼 검증·저장을 하지 않고 잠근 현재 일정으로 상담을 기록한다. 상담 추가를 요청했는데 결과·내용이 비어 있으면 오류이며 빈 상담 생략으로 성공 처리하지 않는다.

상담·이력 저장 실패는 요청 저장 전체를 rollback한다. 서비스나 모델의 ValidationError는 transaction 밖에서 적절한 폼 오류로 매핑하고 사용자 입력을 유지한다. 알 수 없는 DB 오류를 성공 처리하거나 예외 원문을 화면에 노출하지 않는다. 성공은 메시지와 함께 상세 GET으로 redirect해 새로고침으로 상담이 중복 추가되지 않게 한다. 이는 POST 재전송 전반에 대한 idempotency 보장은 아니다.

### 5. 메일은 관련 조회 권한으로 제한한 읽기 전용 영역이다

`notification`의 기존 상태 label, mode, due_at, attempt_count, simulated_at, sent_at, error_code를 사용한다. accepted는 SES 접수이고 실제 전달 확인이 아니라는 안내를 제공한다. unknown과 suppressed도 그대로 구분하며 오류 원문·큐 payload·발송 제어 버튼은 표시하지 않는다. 상세 최초 GET에서 현재 상태를 렌더링하고 이후 수동 새로고침 버튼의 Ajax GET으로 이메일 영역만 갱신한다. 자동 polling은 도입하지 않는다. 구체적인 요청·오류 처리는 아래 Decisions 8을 따른다.

### 6. 기존 정적 자산과 검증 도구를 사용한다

전용 base는 기존 색상·서체·Tailwind CSS를 사용하되 공개 홍보용 header/footer와 분리한다. 서버 렌더링으로 구현하고 메뉴 접기는 우선 native HTML 기능으로 구성한다. 이메일 부분 갱신은 설치된 Axios와 `frontend/entries/backoffice-detail.js`를 사용하며 상세 화면에서만 로드한다. 새 UI·JavaScript 패키지는 추가하지 않는다. `npm run build`로 CSS·JS·source map·라이선스 고지를 함께 동기화한다. 개인정보 페이지와 부분 응답에는 비공개·캐시 금지를 적용하고 template 기본 escape·CSRF를 유지한다.

PostgreSQL 실제 ORM을 사용하는 백오피스 테스트와 기존 admin·신청 관리·알림 테스트를 검증한다. 권한 경계 추가이므로 별도 관점의 권한/직접 POST 검토를 수행하고 발견된 blocking defect만 해결한다. 브라우저에서 360/390/768/1280px·키보드·오류 입력 보존·공유 세션을 확인한다.

### 7. 공개 레이아웃을 참고해 확장 가능한 공통 화면 틀을 구성한다

다음 공개 자료의 navigation·본문 배치와 반응형 전환을 참고한다. 외부 템플릿 전체를 도입하는 대신 필요한 배치 원칙을 기존 Django Templates·Tailwind로 구현하여 현재 빌드·의존성 구성을 유지한다.

- [Flowbite Admin Dashboard](https://github.com/themesberg/flowbite-admin-dashboard): 공개 백오피스 예제로서 사이드바·상단바·목록과 폼의 정보 구성을 참고한다.
- [Tailwind의 Catalyst application layouts 소개](https://tailwindcss.com/blog/2024-05-24-catalyst-application-layouts): desktop 사이드바가 작은 화면에서 접이식 메뉴로 바뀌는 구성과 제목·정보 영역의 구분을 참고한다.

desktop은 왼쪽 사이드바, 상단 페이지 제목·사용자 메뉴, 본문으로 구성한다. 모바일은 상단의 접이식 메뉴와 한 열 본문으로 전환하고 검색·필터·입력 폼도 너비에 맞춰 재배치한다. 로그인 화면은 업무 navigation 없이 같은 색상·서체·폼 스타일을 사용한다.

목록은 페이지 제목, 검색·필터, 신청 목록, 페이지네이션을 구분한다. 상세는 신청 정보·상담 기록·이메일 상태를 제목이 있는 영역으로 나누고 좁은 화면에서 한 열로 표시한다. 상태 badge·입력·버튼·오류 안내의 표현은 화면 간에 일관되게 적용한다.

`backoffice/base.html`에서 navigation·페이지 제목·본문 영역을 template block/include로 분리한다. 향후 기능은 공통 틀을 유지한 채 메뉴 항목과 본문 template를 추가할 수 있게 하며, 현재는 구현됐고 권한이 허용된 메뉴만 표시한다. 미래 기능용 빈 메뉴·통계·설정 화면이나 동적 메뉴 등록 체계는 만들지 않는다. 메뉴를 연 상태와 닫은 상태의 키보드 접근·focus 및 현재 위치 표시를 검증한다.

### 8. 페이지 전환·저장과 부분 갱신의 책임을 나눈다

| 기능 | 요청과 화면 처리 |
| --- | --- |
| 로그인·로그아웃 | 일반 POST 후 안전한 업무 주소 또는 로그인 화면으로 이동 |
| 목록·상세·Django admin 이동 | 일반 GET으로 전체 페이지 전환 |
| 검색·필터·페이지네이션 | 일반 GET과 query string으로 조건을 보존 |
| 신청 정정·상태·재연락·상담 저장 | 일반 POST, 유효성 오류는 입력을 유지해 렌더링하고 성공은 상세 GET으로 redirect |
| 이메일 상태 새로고침 | Ajax GET으로 이메일 표시 영역만 교체 |
| 모바일 메뉴·입력 영역 펼치기 | native HTML 등 브라우저 내 동작으로 처리, 서버 요청 없음 |

신청 상태만 별도의 Ajax 저장으로 분리하지 않는다. 신청·상담을 함께 저장하는 현재 transaction 계약과 작성 흐름을 유지한다. 검색 목록의 부분 갱신이나 History API는 이번 범위에 넣지 않는다.

`/backoffice/applications/<int:pk>/email-status/`에 GET 전용 view를 추가한다. 활성 staff·부모 신청 조회·이메일 조회 권한을 매 요청 확인하고 이메일 영역의 공유 partial template만 HTML로 반환한다. 이는 백오피스 전용 화면 조각이며 별도 REST API나 공개 개인정보 조회를 만들지 않는다. 상태 확인은 DB 조회만 수행하고 발송·신청 변경을 일으키지 않는다.

부분 조회의 미인증·세션 만료는 401, 인가 실패는 403으로 응답하고 로그인 HTML로 redirect하지 않는다. Axios는 성공 시에만 이메일 표시 영역을 교체하며 신청·상담 폼과 새로고침 버튼의 focus를 유지한다. 요청 중에는 버튼을 비활성화하고 진행 상태를 알린다. timeout·네트워크/서버 오류는 기존 표시를 남기되 최신 조회 실패를 알리고 수동 재시도를 제공한다. 401은 재로그인 필요와 별도 탭 로그인 링크를, 403은 접근 거부를 안내한다. 오류 응답을 이메일 내용으로 삽입하거나 자동 페이지 이동·재전송을 하지 않는다.

JavaScript가 없거나 로드되지 않아도 최초 상세에서 이메일 상태 조회와 일반 폼 저장은 가능하다. 부분 갱신 기능만 비활성 상태로 안내하고 현재 상태는 상세 재조회로 확인할 수 있게 한다. 세션 만료 뒤 다른 탭에서 재로그인해도 기존 폼 POST는 CSRF 검증을 그대로 따르며 자동 저장·자동 재전송하지 않는다.

입력 보존은 일반 폼 유효성 오류와 Ajax 갱신 실패를 대상으로 한다. 일반 저장 POST의 세션 만료·CSRF 실패는 저장되지 않았음을 안내하는 오류 화면으로 종료하고 POST 개인정보를 오류 화면에 다시 표시하거나 자동 복구하지 않는다. 프로젝트 전용 오류 안내를 연결할 경우 기존 공개 신청·admin의 CSRF 거부 처리를 유지한다.

## Risks / Trade-offs

- 공유 로그아웃이 다른 관리자 화면에도 적용됨 → 로그인 안내와 README에 명시하고 회귀 테스트한다.
- 일반 저장 POST의 세션·CSRF 실패에는 작성 내용 자동 복구가 없음 → 미저장 안내와 수동 재로그인만 제공하고 원문 POST 개인정보를 오류 화면에 재출력하지 않는다.
- 기존 ModelForm이 검증 중 인스턴스를 변경함 → POST 폼 검증 전 최신 안내·신청을 잠그고 최종 저장 서비스의 재검증을 유지한다.
- 두 담당자가 동시에 편집하면 앞선 변경을 뒤의 제출이 덮어쓸 수 있음 → 기존 저장 정책을 유지하며 신규 충돌 감지는 범위에 넣지 않는다.
- 이메일 접수와 실제 전달을 혼동할 수 있음 → 기존 상태와 시각을 구분하고 전달 확인 미지원 문구를 표시한다.
- 상태 조회 실패 시 예전 값이 최신으로 오인될 수 있음 → 기존 표시를 유지하면서 새로고침 실패를 명시하고 수동 재시도만 제공한다.
- 작은 화면에서 정보가 많은 목록이 넘칠 수 있음 → 반응형 행/카드 배치로 필수 정보를 유지하고 실제 브라우저로 확인한다.

## Migration Plan

schema migration이나 데이터 변환은 없다. URL·화면·CSS·테스트·관련 문서를 함께 반영하고 기존 관리자 계정으로 검증한다. 적용을 되돌려도 저장된 신청·상담·이력은 기존 admin에서 계속 조회할 수 있다. 구현 시 README의 두 진입점·권한·공유 로그아웃과 검증 가이드의 실제 확인 범위, 아키텍처·운영 문서의 관련 설명만 동기화한다.
