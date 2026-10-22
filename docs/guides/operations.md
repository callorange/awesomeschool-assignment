# 운영 가이드

[README](../../README.md)는 로컬 평가 실행의 기본 경로입니다. 이 문서는 구현된 운영 설정·백그라운드 정책·장애 대응을 설명합니다. **배포 완료 보고서가 아니며 AWS 자원 생성·실발송·S3 쓰기는 수행하지 않았습니다.** 구조 규약은 [아키텍처](../architecture.md), 개발 절차는 [개발 규약](../development.md)을 따릅니다.

| 읽는 목적 | 바로가기 |
| --- | --- |
| 로컬 검토·문제 해결 | [계정·권한](#백오피스-계정과-요청-처리) · [신청 샘플 준비](#개발용-신청-샘플) · [로컬 문제 해결·화면 자산 수정](#로컬-문제-해결화면-자산-수정) · [초기 DB 안내](#초기-migration과-개발-db-재생성) |
| 운영 설정·설계 확인 | [개발/운영 환경](#설정과-실행-환경) · [AWS 준비](#aws-운영-준비와-제외-범위) · [worker·메일 상태](#백그라운드-worker와-자동-안내) · [신청 변경과 안내](#신청-관리와-안내-변경) · [이미지 관리](#이미지초기-데이터) · [task 경로 변경](#task-경로-변경-시-운영-절차) |

기능을 직접 확인하는 순서는 [기능 검증 가이드](verification.md)를 참고하세요. 아래 운영 명령은 해당 환경을 준비한 경우에만 사용합니다.

## 백오피스 계정과 요청 처리

기존 `createsuperuser`로 만든 계정은 `/backoffice/`와 `/admin/`에서 함께 사용합니다. 별도 회원가입은 없습니다. 두 화면은 Django 세션을 공유하므로 어느 쪽의 POST 로그아웃도 다른 쪽에 적용됩니다. 일반 담당자는 admin에서 활성 staff로 지정하고 신청 조회 권한을 부여합니다. 신청 변경·상담 조회·상담 추가·상담 안내 이메일 조회는 필요한 모델 권한만 추가합니다. 상담 정정에는 조회·추가가 모두 필요합니다.

| 업무 | 필요한 모델 권한 |
| --- | --- |
| 목록·상세 조회 | `education.view_educationapplication` |
| 신청 변경 | 신청 조회 + `education.change_educationapplication` |
| 상담 조회 | 신청 조회 + `education.view_consultationrecord` |
| 상담 추가 | 신청 조회 + `education.add_consultationrecord` |
| 상담 정정 추가 | 신청 조회 + 상담 조회·추가 |
| 이메일 처리 상태 조회 | 신청 조회 + `education.view_educationapplicationreminderemail` |

모든 업무는 활성 staff 계정을 전제로 합니다. 신청과 상담을 함께 저장하려면 두 작업의 권한이 모두 필요합니다.

신청 변경 권한은 수정 폼과 **변경사항 저장**, 상담 추가 권한만 있으면 읽기 전용 신청과 **상담 추가**를 제공합니다. 통합 저장의 **상담 기록도 추가**는 기본 해제이고 선택한 경우에만 결과·내용을 필수 검증하여 함께 저장합니다. 상담 전용 추가는 항상 필수 입력을 검사하고 신청 값을 수정하지 않습니다.

업무 페이지·검색·필터·페이지 이동은 일반 GET, 로그인·로그아웃·신청/상담 저장은 POST입니다. 이메일 조회 권한이 있는 상세의 수동 새로고침만 Ajax GET으로 이메일 영역을 갱신합니다. 실패 시 기존 표시가 최신이 아닐 수 있음을 알리고 작성 입력을 유지합니다. 세션 만료는 별도 탭 재로그인을 안내하고 권한 거부는 별도 표시합니다. 자동 polling·재발송·task 제어는 하지 않습니다.

일반 저장의 세션·CSRF 검증 실패는 저장 없는 403 안내로 끝납니다. POST 개인정보는 오류 화면에 재출력하지 않고 작성 내용 자동 복구·재전송도 제공하지 않습니다. 다른 탭에서 다시 로그인한 후 기존 폼을 제출할 때도 정상 CSRF 검증이 필요합니다. JavaScript가 없으면 최초 이메일 상태 조회와 일반 저장은 가능하고 부분 갱신만 사용할 수 없습니다.

저장 중 DB 오류는 예외 원문·POST 개인정보가 없는 500 안내를 표시합니다. 자동 재제출하지 않으며 신청 목록에서 상세를 다시 열어 현재 신청·상담 기록을 확인한 후 필요한 변경만 다시 입력합니다. 이메일 부분 조회 오류는 업무 저장 오류와 별개입니다.

## 설정과 실행 환경

| 구분 | 개발 기본값 | 운영 설정 |
| --- | --- | --- |
| 설정 모듈 | config.settings.dev | config.settings.prod |
| 미디어 | 로컬 media/·DEBUG에서 /media/ 제공 | 비공개 S3·CloudFront HTTPS URL |
| 이메일 | locmem·simulated 기록 | django-ses·SES API 접수 결과 기록 |
| 큐 | PostgreSQL ORM broker·default 큐 | 같은 구성, 웹·worker의 DB/서명 설정 일치 필요 |

Django가 저장소 루트 `.env`를 자동으로 읽고 이미 주입된 환경 변수를 우선합니다. uv의 `--env-file`이나 Bash의 `source .env`는 필요하지 않습니다. 필수 secret key·DB 이름/사용자/비밀번호가 없거나 비면 설정 오류로 중단합니다. DEBUG 기본값은 false이며 README의 개발 `.env.example`은 true로 설정합니다.

설정 모듈은 `.env`를 읽기 전에 선택합니다. 운영은 프로세스 환경에 `DJANGO_SETTINGS_MODULE`을 주입하거나 명령의 `--settings`로 지정합니다. `.env`에 설정 모듈을 넣어 자동 전환하는 구조는 아닙니다.

```bash
# 운영 의존성만 설치. 이후 실행은 설치 구성을 유지하도록 --no-sync 사용
uv sync --locked --no-default-groups --group prod
uv run --no-sync python src/manage.py check --settings=config.settings.prod
```

기본 `uv sync --locked`는 공통·dev 및 dev에 포함된 prod 패키지를 설치합니다. AWS 패키지가 설치되어 있어도 dev는 AWS backend·credential을 조회하지 않습니다. 프로젝트 자체는 uv 비패키지 애플리케이션입니다.

## AWS 운영 준비와 제외 범위

공통 DB·secret 외에 다음 운영 값을 준비해야 합니다. 실제 `.env`와 credential은 Git에 넣지 않습니다.

| 값 | 의미 |
| --- | --- |
| DJANGO_DEBUG=false | 운영 DEBUG 활성화 거부 |
| DJANGO_ALLOWED_HOSTS | 운영 host 명시, 빈 값·와일드카드 거부 |
| AWS_STORAGE_BUCKET_NAME·AWS_S3_REGION_NAME | 미디어 버킷·리전 |
| AWS_S3_CUSTOM_DOMAIN | scheme·경로·끝 슬래시 없는 CloudFront host |
| AWS_SES_REGION_NAME | SES 발송 리전 |
| DEFAULT_FROM_EMAIL | SES에서 검증한 발신 이메일 주소 |
| SES_MAX_SEND_RATE | 계정 한도 이하의 유한한 양수, 다른 발신자의 사용량도 고려 |

앱은 IAM role 등 SDK 기본 credential chain을 사용합니다. S3 비공개 버킷·CloudFront OAC·공개 viewer 접근, SES verified identity·발송 권한·sandbox 여부·발송 한도는 운영자가 준비해야 합니다. 설정 오류 시 로컬 저장소나 모의 메일로 fallback하지 않습니다.

설정 전환으로 기존 로컬 이미지를 S3에 복사하지 않습니다. 다음 seed 명령은 **준비된 운영 S3에 이미지를 쓰는 명시적 작업**이므로 로컬 검토에 필요하지 않습니다.

```bash
uv run --no-sync python src/manage.py seed_educations --settings=config.settings.prod
```

정적 파일은 dev·prod 모두 로컬 StaticFilesStorage를 사용합니다. 아래 명령으로 `src/static/`과 Django admin 등 설치 앱의 자산을 저장소 루트의 `staticfiles/`(`STATIC_ROOT`)에 수집합니다. 수집 결과는 Git에서 제외하며 원본과 미디어는 별도로 유지합니다.

```bash
uv run --no-sync python src/manage.py collectstatic --noinput --settings=config.settings.prod
```

운영에서는 Nginx 등 웹 서버가 `/static/` 요청을 이 디렉터리로 연결하도록 설정해야 합니다. Django `urls.py`에 정적 파일 URL을 추가하지 않으며 실제 웹 서버/서비스 관리자·HTTPS 배포는 별도 범위입니다. S3/SES backend 설정과 정적 파일 수집만으로 운영 배포가 완료된 것은 아닙니다. SNS·SQS·웹훅·configuration set은 현재 요구하지 않으며 실제 전달·반송 확인이 필요할 때 후속 연동합니다.

## 백그라운드 worker와 자동 안내

스케줄 준비와 worker 실행을 구분합니다. 운영에서는 같은 prod 설정으로 각각 실행합니다.

```bash
uv run --no-sync python src/manage.py configure_background_tasks --settings=config.settings.prod
uv run --no-sync python src/manage.py qcluster --settings=config.settings.prod
```

준비 명령은 `education-notifications` 스케줄을 재사용해 5분 검사·무제한 반복·default cluster를 설정합니다. 기존 다음 실행 시각은 유지합니다. admin의 주기·반복·cluster 수정을 준비 명령 재실행이 덮어쓸 수 있습니다. import·AppConfig.ready에서 스케줄을 만들지 않습니다.

Q2는 기본 큐 하나와 qcluster 하나를 사용하고 worker 2개가 메일·이미지를 함께 처리합니다. ORM broker alias는 앱과 같은 default입니다. bulk=1·내부 queue_limit=2·task timeout=60초·broker retry=300초·max_attempts=3·ack_failures=True·catch_up=False입니다. catch_up=False는 중단 중 검사 횟수를 몰아 실행하지 않는 설정이며 미처리 신청 자체는 DB에서 재발견합니다.

웹·worker는 같은 DB·서명 키·MEDIA_ROOT 또는 S3 설정을 사용해야 합니다. worker 수나 설정을 변경하면 정상 종료 후 재시작합니다. Ctrl+C·Linux SIGTERM 후 내부 대기·실행 작업과 결과 저장이 끝날 때까지 기다리며 서비스 관리자의 종료 유예 시간도 확보해야 합니다. Windows run-once·강제 종료 복구 검증을 Linux 신호 검증으로 대신하지 않습니다.

### 대상 등록과 전송 상태

연락 가능 날짜의 Asia/Seoul 09시와 신청 생성 시각 중 늦은 때부터 대상입니다. 먼저 10분 이상 남은 queued를 pending으로, 결과 없는 sending을 unknown으로 복구합니다. due_at·PK 순으로 최대 100건씩 잠그고 안내 상태·큐 등록을 같은 transaction에 저장합니다. 실행 예산 20초 동안 batch를 이어 처리하며 필요하면 후속 검사 하나를 등록합니다. 메일 queued가 200건 이상이면 다음 검사까지 등록을 멈춥니다. 이 한도는 Q2 내부 queue_limit=2와 다릅니다.

| 상태 | 의미·다음 동작 |
| --- | --- |
| pending | 시도 전 대기, 최초 횟수 0·MailAttempt 없음 |
| queued | 이번 큐 등록의 전송 시도 전, 재시도 이력·횟수는 유지 |
| sending | 처리권·새 attempt_id·시도 횟수 commit 후 전송 경계 진입 |
| simulated | 개발 모의 완료, simulated_at만 기록, 외부 전송 없음 |
| accepted | 반환 1과 SES MessageId 확인, sent_at·ID 기록. 실제 전달 성공은 아님 |
| retry_wait | 확정 미접수 일시 오류 또는 공유 예산 대기, next_retry_at 이후 대상 |
| failed | 확정 실패·설정 문제·시도 한도 초과, 자동 무한 재시도 없음 |
| unknown | 접수 여부 불명, 증거 없이 자동 재발송·성공 판정하지 않음 |
| suppressed | 완료·취소로 미처리 안내 중단, 상담을 재개해도 자동 발송 재개 없음 |

동일 안내의 처리권을 row lock으로 확보하고 외부 전송 전에 commit합니다. 결과는 현재 attempt_id·예상 상태가 일치할 때 안내·시도 기록에 함께 반영합니다. accepted·simulated를 늦은 실패로 덮어쓰지 않으며 unknown은 같은 시도의 늦은 성공 응답·MessageId가 있을 때만 accepted로 복구합니다. 결과 저장 DB 장애는 sending을 남겨 이후 unknown으로 보존합니다.

### 재시도·전송 속도

- 확정 미접수 일반 일시 오류는 첫 실패 후 5분, 두 번째 후 15분부터 재시도합니다. 일일 한도 초과는 각 실패 후 24시간 대기합니다. 실제 재시도는 검사·큐 상황에 따라 늦어질 수 있습니다.
- 최초 포함 총 3회이며 오류 종류가 바뀌어도 횟수를 초기화하지 않습니다. 24시간은 보수적인 프로젝트 정책이고 SES의 고정 초기화 시각을 뜻하지 않습니다.
- 인증·발신자·유효성 오류는 failed입니다. read timeout·불명확한 오류·전송 후 기록 실패·worker 중단은 unknown으로 남겨 자동 재발송하지 않습니다.
- SES의 worker 공통 DB 예산을 짧은 row lock으로 확보합니다. lock 밖에서 최대 5초만 기다리고 더 긴 대기는 retry_wait로 넘깁니다. 예산 미확보는 시도 횟수를 늘리지 않습니다.
- django-ses 프로세스별 throttle은 끄고 SDK는 연결 5초·읽기 15초·총 호출 시도 1회로 제한합니다. 발송·결과 분류를 우회하는 자동 네트워크 재시도를 막습니다.
- Q2의 실패 목록을 메일 자동 재발송 원본으로 삼지 않습니다. 오류 원문·수신자·본문 대신 안전한 코드·attempt ID를 기록합니다.

운영 조회 명령도 같은 설정으로 실행합니다. 상태별 건수와 확인 대상 식별자만 출력하며 개인정보·상태 변경·수동 재발송을 제공하지 않습니다.

```bash
uv run --no-sync python src/manage.py notification_status --settings=config.settings.prod
```

실제 전송 backend는 `MAILERS["default"]["BACKEND"]`로 결정합니다. 안내 생성 시 저장한 mode는 `NOTIFICATION_MODE`와 일치하는지 확인하는 환경 구분값입니다. record의 mode를 바꿔 backend를 선택하는 구조가 아니므로 로컬에서도 prod 설정을 사용하면 SES backend가 선택됩니다.

`MailSendBudget`은 SES 모드의 첫 claim에서 PK=1로 자동 생성하며 이후 worker가 같은 row를 잠가 공유합니다. 개발 simulated 경로는 이 row를 생성하지 않으므로 admin에 데이터가 없어도 정상입니다. `MailAttempt`는 실제 전송 처리권을 확보할 때 생성하며 Q2 task의 실행 결과와 별도로 전송 증거를 보존합니다.

개발·운영은 DB를 분리합니다. 개발 simulated 기록을 운영에서 재발송하지 않습니다. 본문은 한국어 HTML·일반 텍스트이며 지연되어도 선택 날짜를 사실대로 표시하고 교육 일정 확정으로 표현하지 않습니다.

## 이미지·초기 데이터

옵션 없는 `seed_educations`는 `presets/education/`의 교육 JSON·이미지를 사전 검증하고 없는 교육만 추가합니다. 기존 운영 정보·이미지는 보존합니다. 개발 환경에서 신청·상담·모의 메일 사례도 준비하려면 [개발용 신청 샘플](#개발용-신청-샘플)의 선택 옵션과 기존 staff를 지정합니다. 원본 폴더는 배포물에도 포함해야 하며 일반 static이나 실행 중 업로드 파일로 사용하지 않습니다.

이미지는 교육별 고정 UUIDv7 media_id 폴더에 저장합니다. 프리셋 파일은 내용 SHA256을 파일명으로 사용해 실패 후 남은 파일을 재사용하고 일반 업로드는 UUID 파일명을 사용합니다. slug 변경·초기화 재실행으로 기존 키를 이동하지 않으며 로컬·S3의 덮어쓰기를 허용하지 않습니다.

일반 Education.save의 이미지 교체와 단일/일괄 삭제는 같은 DB transaction에 정리 키·Storage/DB alias를 Q2 ORM 큐에 기록합니다. enqueue 실패는 교육 변경도 rollback합니다. commit 후 작업이 현재 참조를 재검사하므로 공유·재연결 파일은 보존하고 미참조 파일만 삭제합니다. 없는 파일은 성공이며 다른 삭제 오류는 ack_failure=False로 총 3회 시도 후 Q2 실패 기록에 남깁니다. S3 I/O도 연결 5초·읽기 15초·총 시도 1회로 제한합니다.

QuerySet.update·bulk_update·직접 SQL은 signal을 우회합니다. 새 파일 저장 후 DB rollback·프로세스 중단으로 고아 파일이 남을 수 있으며 전수 청소·프리셋 원본 삭제·별도 DLQ는 제공하지 않습니다. 초기화 실패 파일 재사용과 이미지 실패 재등록 시 참조 검사는 유지합니다.

## task 경로 변경 시 운영 절차

현재 `tasks/` 패키지 분리는 `tasks/__init__.py`에서 기존 세 함수를 공개하므로 스케줄·큐의 `education.tasks.<함수명>` 경로는 유지합니다. 이 구조 변경만으로 스케줄 재등록·서명된 payload 편집은 필요하지 않습니다. 코드 배치 후에는 기존 worker를 정상 종료하고 새 코드로 재시작합니다. Django Q2 1.11의 실패 결과는 예외 객체 대신 traceback 문자열이므로 `SafeTaskError` 모듈 이동 때문에 기존 실패 기록을 변환하지 않습니다.

Q2는 함수 경로를 스케줄·큐·실패 기록에 저장합니다. task 함수나 모듈 경로를 변경할 때는 해당 경로를 사용하는 영속 작업이 있는 환경에서 다음 절차를 적용합니다.

1. 스케줄·큐·실행 작업을 확인하고 변경 대상 작업의 신규 등록을 멈춥니다. 주기 스케줄은 admin의 repeats=0으로 중지하며 웹 요청 등 다른 등록 경로도 제어합니다.
2. 기존 코드의 worker로 대기·실행 작업과 결과 저장을 마친 뒤 정상 종료합니다. 서명된 큐 payload를 편집하거나 작업·신청·발송 이력을 지우지 않습니다.
3. 새 코드를 배치하고 영속 스케줄이 새 함수 경로를 참조하도록 갱신합니다. 상담 안내 스케줄은 `configure_background_tasks`로 갱신할 수 있으며 row·next_run을 유지하되 주기·반복·cluster를 기본값으로 설정하므로 운영 설정을 확인합니다. 이후 worker·신규 등록을 재개합니다.

실패한 이미지 작업을 다시 등록할 때는 원인을 해결하고 유효한 현재 task 경로와 원래 args·kwargs, ack_failure=False를 사용합니다. 재등록 작업도 현재 이미지 참조를 검사해야 합니다. 메일 실패·unknown은 경로 변경을 이유로 수동 재발송하지 않습니다.

## 로컬 문제 해결·화면 자산 수정

| 증상 | 확인 방법 |
| --- | --- |
| DB 연결 실패 | `docker compose ps`와 `.env`의 host·port·계정 확인. 기존 volume의 비밀번호는 환경 변수 변경만으로 바뀌지 않음 |
| 설정 모드·값이 예상과 다름 | 프로세스 환경이 `.env`보다 우선함. 기존 DJANGO_SETTINGS_MODULE·DJANGO_DEBUG 주입 여부 확인 |
| CSS·이미지가 보이지 않음 | dev·DEBUG=true 확인, /static/css/site.css·/media/ 응답 확인. prod 미디어는 로컬 파일을 자동 복사하지 않음 |
| 안내가 pending에 머묾 | 스케줄 등록·qcluster 실행·한국 날짜 09시·다음 검사/큐 대기 확인 |
| unknown·failed 발생 | notification_status·Q2 기록의 안전한 코드 확인. 근거 없는 상태 변경·자동 재발송 금지 |
| Python 변경이 반영되지 않음 | --noreload로 실행했다면 웹 서버 재시작. worker는 설정·코드 변경 후 정상 재시작 |

```bash
docker compose ps
uv run python src/manage.py findstatic css/site.css --verbosity 2
```

로컬 staticfiles는 DEBUG runserver가 프로젝트·설치 앱의 자산을 찾아 제공합니다. 따라서 로컬은 collectstatic 없이 관리자 CSS도 표시합니다. 이는 운영용 static 배포가 아닙니다.

평가 실행에는 Node.js가 필요 없습니다. 화면 자산을 수정하는 개발자는 Node.js 20 이상에서 다음 명령을 사용합니다. `frontend/styles.css`·`frontend/entries/`의 JavaScript를 편집하고 저장소에 생성물과 lockfile을 함께 반영하며 `src/static/`의 빌드 결과물을 직접 편집하지 않습니다.

```bash
npm ci
npm run build
```

통합 빌드는 CSS와 진입점별 JS·필요한 공통 chunk·source map·라이선스 고지를 생성합니다. JavaScript 패키지는 필요한 소스에서 import하고, 새 페이지는 `frontend/entries/`에 진입 파일을 추가한 뒤 해당 template에서만 로드합니다. 둘 다 같은 `npm run build`를 사용합니다. 파일 배치와 전체·영역·페이지별 로딩은 [아키텍처](../architecture.md#javascript-진입점과-페이지별-로딩)를 따릅니다. CSS 변경 감시는 `npm run watch:css`, JavaScript는 별도 터미널의 `npm run watch:js`입니다. 빌드·배포 자산의 상세 규칙은 [개발 규약](../development.md#tailwind-css와-화면-검증)을 따릅니다. 종료는 `docker compose down`으로 데이터를 보존하며 volume을 삭제하지 않습니다.

## 신청 관리와 안내 변경

미처리(pending·queued·retry_wait) 신청의 이름·이메일 정정은 다음 발송에 반영합니다. 연락 가능 날짜를 실제로 정정하면 같은 안내의 due_at을 해당 날짜의 한국 시각 09시와 신청 시각 중 늦은 값으로 조정합니다. 메일의 교육명은 접수 당시 snapshot을 유지하고 이름·이메일·연락 가능 날짜는 정정한 현재 값을 사용합니다. 시도 횟수·재시도 허용 시각·전송 모드는 초기화하지 않습니다. 재연락 일정만 바꾸는 것은 안내에 영향을 주지 않습니다.

완료·취소 시 미처리 안내는 **suppressed / 발송 중단**으로 보존합니다. 이미 큐에 있는 작업도 새 시도나 전송을 하지 않으며 재개한 상담에도 안내를 자동 재개하지 않습니다. accepted·simulated·unknown·failed의 기존 증거는 유지합니다. 수동 재발송·재연락 자동 알림은 제공하지 않습니다.

sending 동안은 이름·이메일·연락 가능 날짜 정정과 완료·취소를 거부합니다. 주소·상담 기록·재연락 일정은 변경할 수 있습니다. 발송 결과가 저장되거나 기존 10분 만료 복구로 unknown이 된 뒤 다시 종료할 수 있습니다. 이미 외부 전송된 메일을 회수하거나 미발송이라고 보장하지 않습니다.

## 초기 migration과 개발 DB 재생성

프로젝트 소유 `education` 앱의 migration은 전체 최종 모델을 담은 `0001_initial.py` 하나입니다. Django·Django Q2 패키지의 migration은 그대로 사용합니다. 이전 개발 migration 이력과 호환되지 않으므로 기존 DB에서 `--fake`로 적용하지 않습니다. 공유·운영 DB는 이 초기 migration으로 업그레이드할 수 없으며 별도 전환 설계가 필요합니다.

개발 DB를 초기화하면 교육·신청·상담·메일 증거·사용자/그룹 권한·계정·세션·Q2 작업과 스케줄도 사라집니다. `migrate`·`seed_educations`·`configure_background_tasks`는 DB 삭제 명령이 아니며, 이미 현재 schema가 있는 DB에서 재실행해도 신청·상담 기록을 초기화하지 않습니다. 미디어 파일과 프리셋 원본은 DB와 별도로 관리합니다. migration 정리와 데이터 초기화의 승인 기준은 [개발 규약](../development.md#마이그레이션-변경과-이력-정리)을 따릅니다.

빈 DB 준비 순서는 다음과 같습니다. 웹·worker를 중지한 상태에서 실행하고 준비 후 같은 코드의 프로세스를 시작합니다.

```bash
uv run python src/manage.py migrate --noinput
uv run python src/manage.py seed_educations
uv run python src/manage.py configure_background_tasks
uv run python src/manage.py createsuperuser
```

교육 프리셋 3개와 `education-notifications` 스케줄(5분 간격·무제한 반복·default cluster)을 준비합니다. 초기화로 관리자 계정도 사라지므로 새로 생성해야 합니다. 신청 admin 경로는 `/admin/education/educationapplication/`, 상담 안내 이메일은 `/admin/education/educationapplicationreminderemail/`입니다. task 경로와 `notification_status` 명령은 유지합니다.

## 개발용 신청 샘플

실제 업무 데이터와 분리한 개발 DB에서 사용합니다. 설정 모듈이 `config.settings.dev`이고 `NOTIFICATION_MODE=simulated`, `MAILERS["default"]["BACKEND"]`가 locmem일 때만 신청 옵션을 허용합니다. DEBUG만으로 허용하지 않으며 운영·외부 발송 backend는 교육/이미지 쓰기 전에 거부합니다. 개발 설정으로 공유 DB에 접속하는 것까지 자동 탐지하지는 않습니다. 옵션 없는 교육 초기화의 운영 S3 계약은 유지합니다.

기존 활성 staff를 먼저 준비하고 qcluster·다른 안내 등록 프로세스를 정상 종료한 후 실행합니다. 계정·권한·비밀번호는 명령이 생성하거나 변경하지 않습니다. 화면 조회에는 신청·상담·이메일 조회 권한, 편집에는 신청 변경·상담 추가 권한이 필요하며 기존 superuser도 사용할 수 있습니다.

```bash
uv run python src/manage.py seed_educations --with-applications --staff-user reviewer
```

`reviewer`를 실제로 준비한 기존 사용자명으로 바꿉니다. staff 누락·미존재·비활성·non-staff와 신청 옵션 없는 `--staff-user`는 오류입니다. 이 계정은 가상 상담 작성자로 연결되며 실제 상담 수행 증거가 아닙니다. 상담은 `[샘플]`로 표시하고 기존 PROTECT 정책에 따라 연결 계정은 삭제 대신 비활성화합니다.

- 교육별 신청은 11·11·10건, 신청 상태는 접수 8·상담중 6·재연락 10·완료 4·취소 4건입니다. 교육·상태가 최신순 목록에서 섞입니다.
- 날짜는 최초 생성 당시 한국 시각 기준입니다. 연락 가능 날짜는 과거·오늘·미래이고 재연락은 오늘 3·지난 날짜 3·미래 날짜 2·미정 2건입니다. 오늘 중 지난 일정은 기한 경과 필터에도 포함됩니다.
- 이름·주소·내용은 가상이고 이메일은 `application-preset-01@example.com`부터 32까지입니다. 상담 없음·부재중·재연락 합의·원기록을 보존한 정정 사례가 있습니다.
- 고정 제출 UUID가 이미 있으면 신청·상담·안내·시도·history 전체를 건너뜁니다. 날짜 이동·상태 복구·누락 종속 기록 수리도 하지 않습니다. 현재 이메일을 정정해도 최초 snapshot으로 식별합니다. 불변 최초 이메일·교육 slug가 충돌하면 오류와 전체 DB rollback으로 처리합니다.
- 일부 샘플만 있으면 없는 신청만 현재 실행 기준으로 추가합니다. 최초 전체 분포는 담당자 편집·날짜 경과·worker 처리 이후 보장하지 않습니다. 일반 신청·계정·기존 교육·미디어는 삭제하거나 초기화하지 않습니다.

이메일은 `pending` 8·`queued` 3·`sending` 2·`simulated` 7·`retry_wait` 3·`failed` 2·`unknown` 3·`suppressed` 4건의 **화면 확인용 합성 상태**입니다. 모든 mode는 simulated이며 실제 발송·Q2 큐/스케줄 등록·공유 전송 예산 생성은 없습니다. `accepted`·SES 접수 시각·MessageId는 만들지 않습니다. 오류 코드는 `preset_simulated_` 접두어로 구분합니다. 합성 MailAttempt도 실제 외부 호출 증거가 아닙니다.

먼저 worker 없이 목록·상세·이메일 상태를 확인하세요. 이후 worker와 정기 검사를 실행하면 도래 pending/retry_wait는 모의 처리되고 합성 queued는 실제 task가 없으므로 10분 만료 후 pending 복구·재등록됩니다. 합성 sending도 10분 만료 후 unknown으로 복구됩니다. 단순 상태 새로고침은 조회만 하고 재실행으로 초기 상태를 복원할 수 없습니다.

실패하면 이번 실행의 새 교육·신청·상담·안내·시도·이력은 함께 rollback됩니다. Storage 쓰기는 DB transaction 밖이므로 파일이 남을 수 있다는 기존 안내·재실행 재사용 계약을 유지하며 자동 삭제하지 않습니다. 교육과 신청의 생성·건너뜀 건수를 따로 출력하며 건너뜀은 기존 데이터 보존을 뜻하고 자동 수리 완료를 뜻하지 않습니다.
