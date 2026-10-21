# Design

## Context

동기는 [proposal.md](proposal.md)를 따른다. 현재 `education` 앱의 models·views는 비어 있고 URL은 `/admin/`만 제공한다. 앱 template 탐색과 staticfiles, PostgreSQL, Django test runner는 이미 설정되어 있다. Node 패키지 manifest와 CSS 빌드는 없으며 기존 smoke test는 DB 연결과 관리자 로그인 HTML을 검증한다.

현재 `config/settings.py`가 공통 설정과 `.env` 로딩을 함께 담당하고 manage.py·ASGI·WSGI가 이를 기본값으로 지정한다. 설정 테스트도 해당 파일을 임시 디렉터리에 복사해 실행하므로 패키지 분리와 함께 테스트 구조를 변경해야 한다. uv는 공통 실행 의존성과 Ruff만 있는 dev 그룹을 사용한다.

새 교육 모델·CSS 개발 도구·환경별 미디어 저장소가 필요하므로 설계를 작성한다. 구현 시 적용되는 Python·Django·HTML/CSS 규칙은 실제 변경 파일에 맞춰 읽으며 template managed 파일은 건드리지 않는다.

## Goals / Non-Goals

**Goals:**
- 기존 단일 Django 구조에서 서버 렌더링으로 완성된 교육 소개 화면을 제공한다.
- CSS를 수정하는 개발 환경과 저장소를 실행하는 평가 환경을 구분하여 실행 준비 부담을 줄인다.
- 초기 데이터는 명시적 명령으로만 넣고 반복 실행 시 사용자 편집 데이터를 보존한다.
- 동일한 모델과 template로 개발 로컬 미디어와 운영 S3·CloudFront를 지원하고 운영 설치에서 개발 도구를 제외한다.

**Non-Goals:**
- SPA·별도 프론트 서버·범용 CMS·자동 콘텐츠 동기화·사용자 파일 업로드 UI는 도입하지 않는다. 프리셋의 미디어 저장은 포함한다.
- 현재 화면에 신청 버튼을 가장한 미작동 링크나 실제 히어로스쿨 문의 전송 기능을 넣지 않는다. 후속 신청 범위는 proposal을 따른다.

## Decisions

### 1. 기존 education 앱의 모델과 서버 렌더링

`Education` 모델 하나를 사용한다. 필드는 고유 slug, 교육명, 한 줄 소개, 대표 이미지 FileField와 대체 텍스트, 교육목표 목록, 추천대상 목록, 시수별 커리큘럼, 원문 URL, 수집일, 표시 순서다. 이미지에는 도메인이나 로컬 절대 경로가 아닌 저장소 상대 이름을 저장하며 template에서 필드의 `.url`을 사용한다. 업로드 UI나 이미지 변환은 없으므로 Pillow 의존성을 요구하는 ImageField는 도입하지 않는다. 목표·대상은 문자열 배열, 커리큘럼은 시수 구성별 교시·주제·활동·설명 배열로 JSONField에 저장한다. 프리셋 입력 시 배열·필수값·교시 순서·이미지 원본 존재를 검증한다. 원문 HTML을 저장하거나 `safe`로 출력하지 않고 template 자동 escaping을 유지한다.

시수는 원문에 있는 구성을 모두 보존한다. 예를 들어 프롬프트는 2·3·4시수, 사회정서 교육은 3·4시수 구성이다. 상세에서는 시수별 제목과 순서 있는 목록을 모두 렌더링한다. 별도 하위 모델과 편집 UI는 현재 요구에 없으므로 추가하지 않는다. JSON 구조는 독립 커리큘럼 검색·편집이 필요한 시점에 재검토한다.

파일만 직접 읽는 방식보다 PostgreSQL 모델을 선택한 이유는 초기 데이터 설정 요구와 향후 신청의 교육 참조를 자연스럽게 지원하기 위해서다. 이번에 신청 모델을 미리 만들지는 않는다. slug는 `prompt-hero`, `emotion-hero`, `relationship-hero`로 고정하고 표시 순서와 slug로 정렬한다.

### 2. 화면 구조와 반응형

`education/urls.py`를 프로젝트 URL에 연결한다. 공통 base를 `src/templates/base.html`, 랜딩·상세를 `src/templates/education/`에 두고 공개 GET view로 렌더링한다. 없는 상세는 404, 빈 목록은 안내 문구로 처리한다.

랜딩은 간결한 내비게이션, 교육 목적을 전달하는 히어로 영역, 프로그램 카드, 출처·과제 안내 footer로 구성한다. 상세는 제목·대표 이미지·소개, 교육목표·대상, 시수별 커리큘럼, 원문 출처 순서다. 범용 대시보드형 UI 대신 교육 내용을 읽고 비교할 수 있는 여백과 제목 위계를 사용한다.

모바일을 기본으로 하고 `md`에서 카드 2열, `lg`에서 3열로 확장한다. 상세의 제목과 이미지는 넓은 화면에서 2열로 구성하되 본문 읽기 폭은 제한한다. 커리큘럼은 표 대신 세로 목록으로 표시하여 모바일에서 가로 스크롤을 피한다. 긴 문구 줄바꿈, 이미지 비율 유지, viewport 설정, 의미 있는 heading·landmark, 포커스 표시, 충분한 링크 간격과 최소 44px 주요 터치 영역을 제공한다. 색상·세부 장식은 구현 시 결정하되 정보 구조와 접근성 기준은 유지한다.

### 3. Tailwind CLI 빌드와 저장소에 포함하는 CSS

[공식 CLI 안내](https://tailwindcss.com/docs/installation/tailwind-cli)에 따라 Tailwind CSS 4 계열과 `@tailwindcss/cli`를 개발 전용 npm 의존성으로 사용하고 package-lock으로 설치 조합을 고정한다. Django Tailwind 연동 패키지나 Vite는 추가하지 않는다.

루트 `package.json`에 `build:css`·`watch:css`를 제공한다. `frontend/styles.css`를 입력으로, `src/static/css/site.css`를 출력으로 사용한다. 통합 `src/templates/`를 명시적인 탐색 대상으로 지정하고 클래스 이름은 완전한 문자열로 작성한다. CSS 출력과 원본·lockfile은 함께 커밋하며 node_modules는 제외한다. `npm ci`와 `npm run build:css`는 CSS를 수정하는 개발자에게만 필요하다.

template는 static 태그로 빌드 CSS를 참조하고 CDN이나 브라우저 내 Tailwind 컴파일을 사용하지 않는다. 기본 시스템 글꼴을 사용하여 외부 글꼴 요청도 피한다. Python 검사는 기존 Ruff 범위를 유지하고 template managed 파일을 CSS 탐색·검사 대상으로 확장하지 않는다.

### 4. 고정 프리셋과 안전한 초기화

`presets/education/education_presets.json`과 `presets/education/images/`에 데이터와 이미지 원본 3개를 포함한다. 원본은 프리셋 입력이며 웹에서 직접 제공하는 static 자산이 아니다. 명령이 선택된 기본 Storage에 저장한다. 출처는 다음 공식 페이지이며 실제 수집 시점에 내용을 재확인한다.

- 프롬프트 히어로: https://www.hero-school.net/visit/prompt/
- 감정탐험 히어로: https://hero-school.net/visit/emotion/
- 관계 히어로: https://hero-school.net/visit/relationship/

프로그램명과 공개 설명을 바탕으로 필요한 소개 문구를 요약·편집하고 출처·수집일·편집 여부를 기록한다. 대표 이미지는 각 원문의 교육 이미지를 확보하며 이미지 원본 URL도 출처 기록에 남긴다. 이미지 확보 가능 여부는 구현 시 확인해야 하며 다른 교육의 이미지를 무관하게 재사용하지 않는다. 공개 정보 중 후기·실제 학생·학교 일정·문의 연락처 데이터는 수집하지 않는다.

관리 명령 `uv run python src/manage.py seed_educations`는 전체 프리셋을 검증한 뒤 기본 Storage로 이미지 원본을 저장하고 DB transaction 안에서 slug 기준으로 없는 교육만 생성한다. 원시 fixture의 고정 PK 로딩은 기존 레코드를 덮어쓸 수 있어 사용하지 않는다. 이미 있는 교육은 이미지까지 건드리지 않는다. 새 교육의 이미지는 교육 slug와 원본 내용 해시를 포함하는 프리셋 전용 이름으로 저장하고 이미 존재하는 동일 이름은 재사용하며 Storage.save가 반환한 이름을 필드에 기록한다. 생성·건너뛴 건수를 보고하며 업데이트·삭제·강제 초기화 옵션은 추가하지 않는다. migration·서버 시작·일반 테스트에서 프리셋을 자동 주입하지 않는다.

입력 오류는 쓰기 전에 거부한다. 저장소 오류나 DB 오류가 발생하면 DB transaction을 롤백하고 명확한 CommandError로 보고한다. 파일시스템·S3 쓰기는 DB transaction에 포함되지 않으므로 먼저 저장한 파일이 남을 수 있다. 자동 삭제로 기존 공유 객체를 훼손하지 않고, 남은 파일은 오류 보고와 재실행 시 재사용으로 처리한다. DB 롤백을 파일·S3 롤백으로 설명하지 않는다. 일반 테스트는 임시 로컬 미디어와 외부 저장소 fake를 사용하고 실제 AWS 업로드는 별도 명시적 opt-in으로 분리한다.

### 5. 공통 설정과 dev·prod 설정 분리

`config/settings.py`를 `config/settings/` 패키지로 바꾸고 빈 `__init__.py`, `base.py`, `dev.py`, `prod.py`로 구성한다. base는 공통 앱·DB·template·지역화·비밀값 검증과 저장소 루트 `.env` 로딩을 담당한다. 파일 깊이 변경에 맞춰 BASE_DIR와 `.env` 경로를 보정하며 프로세스 환경 우선·필수값 누락과 빈 값 거부 계약을 유지한다.

manage.py·ASGI·WSGI는 `os.environ.setdefault`의 기본 모듈을 `config.settings.dev`로 바꾸고 이미 지정된 `DJANGO_SETTINGS_MODULE`을 보존한다. 운영은 실행 프로세스에서 `DJANGO_SETTINGS_MODULE=config.settings.prod`를 명시한다. 관리 명령은 Django의 `--settings=config.settings.prod`도 지원한다. 선택은 settings import 전에 완료되어야 하므로 프로젝트 `.env`의 설정 모듈 값으로 자동 선택한다고 설명하지 않는다. 별도 MEDIA_STORAGE 모드나 자동 환경 추론은 추가하지 않는다.

dev는 Django 기본 FileSystemStorage, 저장소 루트 `media/`와 `/media/`를 사용한다. DEBUG는 기존 DJANGO_DEBUG 파싱과 기본 false 계약을 유지하며 README의 로컬 예시에서 true를 설정한다. DEBUG일 때만 개발 URL에서 미디어를 제공한다. 생성된 media 디렉터리는 Git에서 제외하고 배포에 포함할 이미지 원본은 `presets/education/images/`에 보존한다. dev에서는 AWS 백엔드를 import·초기화하거나 credential·메타데이터를 조회하지 않는다.

prod는 DEBUG=false를 강제하고 DJANGO_DEBUG=true 요청은 설정 오류로 거부한다. S3 버킷·리전·CloudFront 도메인과 명시적인 ALLOWED_HOSTS를 요구하고 누락 시 로컬 저장소로 fallback하지 않는다. `STORAGES['default']`의 BACKEND를 `storages.backends.s3.S3Storage`로 지정하고 OPTIONS로 bucket_name·region_name·custom_domain·location='media'·url_protocol='https:'·default_acl=None·file_overwrite=False·querystring_auth=False를 전달한다. 버킷은 비공개이고 CloudFront OAC를 통해 원본 접근을 허용하며 공개 교육 이미지의 viewer 접근은 서명 없이 제공하는 전제다. 이 설정은 [django-storages S3 문서](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html)와 [AWS OAC 문서](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)를 기준으로 한다.

환경 변수는 `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_S3_CUSTOM_DOMAIN`을 사용한다. 도메인은 scheme·경로·끝 슬래시 없는 host로 검증하며 `.env.example`에는 계약만 기록한다. AWS 권한은 SDK 기본 credential chain과 배포 IAM role을 사용하고 키를 코드·문서에 기록하지 않는다. 앱 IAM은 지정 media prefix에 필요한 읽기·쓰기 범위로 제한하며 이번에 실제 버킷·배포·권한 리소스를 생성하지 않는다.

`STORAGES['staticfiles']`는 기존 Django staticfiles 백엔드를 명시적으로 유지한다. CSS는 static, 교육 이미지는 media라는 책임을 분리하며 운영 CSS 서빙·collectstatic 배포 구성은 이번에 확장하지 않는다. 로컬 미디어를 운영으로 옮기는 기능도 암묵적으로 실행하지 않는다. 프리셋은 prod 모드에서 기존에 준비된 S3로 명시적 seed를 실행해 채울 수 있다.

### 6. uv 의존성 그룹과 설치·실행

공통 `project.dependencies`는 Django·DRF·django-environ·Psycopg를 유지한다. `dependency-groups.prod`에 `django-storages[s3]`를 두고 `dev`는 `{include-group = 'prod'}`와 Ruff를 포함한다. uv의 기본 dev 그룹 동작을 사용하며 local 그룹이나 aws extra는 만들지 않는다. 그룹을 바꾸기 위해 런타임에 pip·uv를 호출하지 않는다. prod 그룹은 [uv 그룹 기능](https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-groups)을 사용하는 이 비패키지 애플리케이션의 운영 설치 선택지다.

- 로컬 개발·평가: `uv sync --locked`로 공통+dev+prod 의존성을 설치하고 기본 dev settings로 실행한다. AWS 패키지가 설치되어 있어도 로컬 저장소만 사용한다.
- 운영: `uv sync --locked --no-default-groups --group prod`로 공통+prod만 설치한다. 이후 기존 환경의 실행 파일을 직접 사용하거나 `uv run --no-sync`를 사용해 기본 dev 그룹이 다시 동기화되지 않게 한다. 실행 전에 prod settings 모듈을 지정한다.
- uv.lock은 양쪽 조합을 함께 고정한다. 임시 환경에서 각 설치의 패키지 집합을 검사하여 운영에는 Ruff가 없고 S3 의존성이 있는지 확인한다. 호환 버전은 구현 때 PyPI 메타데이터와 실제 lock·설치·기능 검사로 검증한다. 현재 django-storages의 공개 classifier만으로 Python 3.14·Django 6.1 호환성을 확정하지 않는다.

### 7. 거버넌스와 개인정보 경계

`docs/architecture.md`의 단일 settings 설명·직접 의존성·화면 기술 선택과 프론트 빌드 예외를 갱신한다. `docs/development.md`에는 Tailwind 소스·생성물 동기화, 반응형, 분리된 settings·저장소 테스트와 dev/prod 설치 검증을 정의한다. README와 `.env.example`에는 평가자용 dev migration → seed → runserver, 개발자용 npm 절차, 운영 그룹 설치·settings 지정·S3 전제를 구분한다. 새 거버넌스 문서를 만들지 않으며 기존 문서 안내의 담당 경계를 유지한다.

화면과 명령은 공개 교육 콘텐츠만 다루며 개인정보나 관리자 계정을 생성하지 않는다. 기존 인증 middleware와 `/admin/` 동작을 유지하고 DB credential 계약은 보존한다. 실제 AWS 연결 검사는 기본 테스트에서 제외하며 비용이 발생하는 리소스 생성·업로드·배포는 계획 수정 작업에서 수행하지 않는다.

## Risks / Trade-offs

- [원문과 이미지의 변경·접근 실패] → 실제 수집 시 확인한 출처와 날짜를 고정하고 로컬 평가 시 외부 요청을 제거한다. 원본 이미지 확보가 막히면 완료로 처리하지 않고 대체안에 대한 사용자 결정을 받는다.
- [파일·S3와 DB의 원자성 차이] → DB 부분 저장을 방지하되 남은 파일 가능성을 보고하고 재실행 시 재사용한다. 기존 파일 자동 삭제나 완전한 분산 transaction은 도입하지 않는다.
- [운영 설치 후 uv run의 기본 그룹 재설치] → 설치 후 직접 실행 또는 `uv run --no-sync` 사용을 문서화하고 운영 패키지 집합을 검증한다.
- [운영 모드만 바꿔도 로컬 이미지가 이동한다고 오해] → DB의 상대 이름은 유지되지만 대상 저장소에 이미지가 별도로 필요함을 설명하고 프리셋만 명시적 seed로 제공한다.
- [프리셋 실행은 기존 교육을 갱신하지 않음] → 사용자 편집 보존을 우선하며 README에 누락 데이터만 채운다는 계약을 명시한다.
- [생성 CSS 누락 또는 오래된 CSS] → template 수정 후 빌드하고 동일 lockfile의 재빌드 결과와 저장소 산출물을 비교한다.
- [JSON 커리큘럼 구조의 DB 수준 검증 제한] → 현재 유일한 입력인 프리셋 명령에서 검증하고 실제 DB 저장·렌더링 테스트를 작성한다.
- [최신 CSS의 브라우저 지원 차이] → 현대 브라우저를 대상으로 확인하고 구형 브라우저 지원을 임의로 약속하지 않는다.

## Migration Plan

1. 기존 테이블을 변경하지 않는 새 교육 테이블 migration을 생성하고 SQL을 확인한다.
2. dev 의존성 설치와 settings 패키지·진입점 전환 후 개발 DB에 migration을 적용하고 명시적 seed 명령으로 로컬 media를 채운다. 기존 사용자·관리자 데이터는 건드리지 않는다.
3. 빌드 CSS와 로컬 미디어로 페이지를 실행하여 서버 테스트와 반응형 화면을 검증한다. prod 의존성 최소 설치와 settings·CloudFront URL 생성은 외부 연결 없이 별도로 검사한다.
4. 향후 운영 배포 시 S3·CloudFront OAC·IAM을 먼저 준비하고 prod 그룹 설치와 settings를 지정한다. 운영 프리셋 업로드는 명시적으로 실행하며 실제 S3 쓰기·CloudFront 응답 검사는 opt-in으로 수행한다. 이 계획 수정에서는 리소스 생성·업로드를 실행하지 않는다.
5. 되돌릴 때는 새 URL 노출과 settings 선택을 조정하고 테이블·파일·객체를 보존한다. 저장소 전환은 데이터 복사를 동반하지 않는다. migration 역적용은 교육 데이터를 삭제하므로 별도 요청 없이 수행하지 않는다.
