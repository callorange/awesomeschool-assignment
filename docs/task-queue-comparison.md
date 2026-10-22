# Celery와 Django Q2 기능 비교

확인일: 2026-10-21. Celery 5.6 stable 문서와 Django Q2 1.11 문서·1.11.1 소스를 기준으로 정리했다. 이 문서는 기술 비교와 선택 기록이며, 설치·설정·실행 검증 완료를 의미하지 않는다. 실제 구현 상태는 [프로젝트 README](../README.md)를 따른다.

## 기능 비교

| 항목 | Celery | Django Q2 |
| --- | --- | --- |
| 기본 실행 구조 | worker가 작업 실행, Beat가 주기 작업 등록을 담당 | `qcluster`가 worker pool·scheduler·작업 수신·결과 저장·프로세스 감시를 함께 관리 |
| broker | Redis·RabbitMQ 등 선택 | Redis 등 외에 Django ORM broker 지원. 기존 PostgreSQL 활용 가능 |
| 주기 작업 | Beat 사용. DB에서 스케줄을 관리하려면 django-celery-beat 선택 가능 | scheduler 내장. Django 모델·admin으로 스케줄 관리 |
| 고정 동시 실행 수 | `--concurrency`로 지정 | `Q_CLUSTER["workers"]`로 지정 |
| 동적 동시 실행 수 | 지원 pool에서 `--autoscale`, `pool_grow`·`pool_shrink` 사용 가능 | 기본 autoscale·실행 중 worker 수 제어 명령 없음. 설정 변경 후 재시작 |
| 여러 큐 소비 | worker 하나가 여러 큐 소비 가능 | 문서화된 기본 구성은 cluster 하나가 해당 이름의 큐 하나를 소비 |
| 큐별 실행 분리 | `worker -Q mail` 등으로 분리 | `qcluster --name mail` 등으로 분리 |
| 개별 설정 | 작업별 retry·timeout과 worker 실행 옵션 등으로 구성 | 공통 `Q_CLUSTER`에 `ALT_CLUSTERS` 옵션을 덮어써 cluster별 구성 |
| 오류별 재시도 | `retry()` 또는 `autoretry_for` 등으로 예외별 정책 작성 | 기본 실패 재전달은 오류 원인을 분류하지 않음. 오류별 정책은 애플리케이션에서 작성 |
| 실패 작업 관리 | result backend·모니터링 도구 등을 선택해 구성 | Django admin에서 실패 결과 확인·수동 재등록 제공 |
| 정상 종료 | `SIGTERM` 또는 첫 `Ctrl+C`로 실행 중인 작업을 기다리는 warm shutdown | `SIGTERM`·`Ctrl+C`로 새 작업 수신 중단 후 내부 대기·실행 작업과 결과 저장을 마치고 종료 |
| 재시작·reload | 정상 종료 후 새 worker 실행 권장. daemon의 `SIGHUP` 재시작은 운영 비권장 | 기본 graceful reload 없음. 정상 종료 후 재시작 |

근거: [Celery worker 관리](https://docs.celeryq.dev/en/stable/userguide/workers.html), [Celery 작업·재시도](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying), [Celery Beat](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), [Q2 실행 구조](https://django-q2.readthedocs.io/en/master/architecture.html), [Q2 설정](https://django-q2.readthedocs.io/en/master/configure.html), [Q2 실패 작업 관리](https://django-q2.readthedocs.io/en/master/admin.html).

## 큐 선택과 실행 명령

### Celery

`-Q`를 생략하면 `task_queues`에 선언된 모든 큐를 소비한다. 별도 선언이 없으면 기본 큐 하나를 사용하며, 그 기본 이름은 `celery`다. 기본 이름은 `task_default_queue`로 바꿀 수 있다. broker의 모든 큐를 자동 탐색하는 의미는 아니다.

다음은 Celery 앱 모듈을 `config`로 구성했다고 가정한 비교용 명령이며, 현재 프로젝트에서 실행 가능한 명령은 아니다.

```shell
celery -A config worker --concurrency=4
celery -A config worker -Q mail,media --concurrency=4
```

첫 명령은 설정된 큐 전체, 두 번째는 mail·media만 소비한다. 두 큐를 소비하는 worker의 동시 실행 수가 4이면 두 큐가 그 실행 자원을 공유하며, 큐마다 4개를 할당하는 것은 아니다. `--concurrency`는 고정값이며 자동 증감은 `--autoscale`의 역할이다. pool·broker에 따라 지원 기능이 다르다.

근거: [Celery 큐 소비](https://docs.celeryq.dev/en/stable/userguide/workers.html#queues), [기본 큐 이름 변경](https://docs.celeryq.dev/en/stable/userguide/routing.html#changing-the-name-of-the-default-queue), [autoscale](https://docs.celeryq.dev/en/stable/userguide/workers.html#autoscaling).

### Django Q2

Q2 설치·설정을 마친 뒤 저장소 루트에서 실행하는 기본 명령은 다음과 같다.

```powershell
uv run python src/manage.py qcluster
```

`--name`과 `Q_CLUSTER_NAME` 환경 변수가 없으면 기본 cluster의 큐 하나를 소비한다. 기본 cluster 이름은 `cluster_name`이 있으면 그 값, 없으면 `name`을 따르며 둘 다 없으면 `default`다. `ALT_CLUSTERS`를 선언해도 모든 cluster가 자동 시작되지 않는다.

여러 큐로 분리한 경우 Windows에서는 각각 별도 실행한다. Linux에서는 공식 문서가 `Q_CLUSTER_NAME` 환경 변수로 이름을 선택하는 방식을 안내한다.

```powershell
uv run python src/manage.py qcluster --name mail
uv run python src/manage.py qcluster --name media
```

공통 옵션은 `Q_CLUSTER`에, 차이만 `ALT_CLUSTERS`에 둔다. 키 이름은 대문자 `ALT_CLUSTERS`이며 옵션 단위로 덮어쓴다. 중첩 딕셔너리의 재귀 병합은 아니다. `name`은 같은 사이트의 서명용 prefix에도 사용되고 실제 대체 큐 선택은 `cluster_name`으로 처리되므로 두 역할을 혼동하지 않는다.

근거: [Q2 여러 큐·cluster](https://django-q2.readthedocs.io/en/master/cluster.html#multiple-queues), [1.11.1 설정 소스](https://github.com/django-q2/django-q2/blob/v1.11.1/django_q/conf.py).

## Q cluster와 worker 프로세스의 차이

`qcluster` 명령 하나가 OS 프로세스 하나라는 뜻은 아니다. 내부에 Sentinel·Pusher·worker들·Monitor가 생성되며 scheduler는 Sentinel에서 실행된다. `workers`는 실제 작업 실행 프로세스 수이며 전체 OS 프로세스 수와 다르다.

같은 PostgreSQL broker·큐 이름·서명 설정을 공유하는 독립된 `qcluster`를 두 개 실행하는 것도 지원한다. 정상 점유 기간에는 작업을 나눠 가져오며 각 작업을 모든 cluster로 복제하지 않는다. 각 cluster가 worker 2개이면 전체 작업 실행 worker는 4개다.

다만 점유 만료나 장애 후에는 같은 작업이 재전달될 수 있다. cluster 수를 하나로 줄여도 이 가능성은 사라지지 않는다.

근거: [Q2 다중 cluster](https://django-q2.readthedocs.io/en/master/cluster.html#multiple-clusters), [Q2 구조](https://django-q2.readthedocs.io/en/master/architecture.html), [1.11.1 cluster 소스](https://github.com/django-q2/django-q2/blob/v1.11.1/django_q/cluster.py).

## 재시도와 중복 실행

Q2의 `ack_failures=False`는 실패한 작업을 broker가 다시 전달할 수 있게 한다. `True`는 실패도 전달 완료로 확인해 큐에서 제거하며, 실행 결과를 성공으로 바꾸는 옵션은 아니다. 작업별 `ack_failure`로 cluster 기본값을 덮어쓸 수 있다. `max_attempts=0`은 무제한이므로 제한이 필요하면 값을 명시한다.

`retry`는 예외 발생 후의 backoff 전용 옵션이 아니라 broker가 완료 확인을 기다리는 시간이다. 작업이 실행 중이거나 내부 큐에서 대기 중이어도 이 시간이 지나면 재전달될 수 있다. `timeout < retry`를 지키고, 내부 대기·실행·결과 저장 시간까지 고려해 `queue_limit`·timeout·retry를 함께 정해야 한다. `ack_failure=True`도 완료 확인 전 프로세스 종료와 같은 모든 재전달을 방지하지는 않는다.

Celery도 정확히 한 번 실행을 자동 보장하지 않는다. 예외에 대한 retry와 broker의 재전달은 별개이며, 기본 실행 전 ACK와 `acks_late` 등의 선택에 따라 장애 시 유실·재실행 특성이 달라진다. 두 도구 모두 중요한 side effect에는 애플리케이션의 중복 방지와 미처리 복구가 필요하다.

메일의 `sent_at` 확인만으로는 동시 worker가 모두 미발송으로 판단하는 상황을 막지 못한다. 고유 발송 기록과 원자적인 처리권 확보가 필요하다. SES가 접수한 뒤 응답 유실·DB 기록 전 종료가 발생하면 실제 발송 여부가 불명확해진다. SES SendEmail에는 idempotency token 인자가 없어 단순 재시도로 중복·누락을 동시에 제거할 수 없다. SES 접수 성공도 수신함 도착을 의미하지 않는다.

오류별 재시도는 실패 결과 문자열을 파싱하기보다 발송 기록의 구조화된 오류 코드로 판단한다. 명확한 미접수 일시 오류만 제한적으로 재시도하고 접수 여부 불명은 확인 필요로 보존하며 자동 재발송하지 않는다. SNS·웹훅을 통한 추가 결과 대조와 반송 확인은 후속 범위다. Django 이메일 API·환경별 backend·상태 전이는 구현했으며 실제 AWS 발송은 검증하지 않았다.

근거: [Q2 retry·ACK 설정](https://django-q2.readthedocs.io/en/master/configure.html#retry), [작업별 ack_failure](https://django-q2.readthedocs.io/en/master/tasks.html#ack-failure), [Celery 작업 ACK·retry](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [SES SendEmail](https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_SendEmail.html).

## 정상 종료와 재시작

Q2는 종료 신호를 받으면 broker에서 새 작업을 가져오는 것을 중단하고, 이미 내부로 가져온 작업을 처리한 뒤 결과 저장·완료 확인을 마친다. broker 전체를 비울 때까지 기다리는 것은 아니다. 작업 timeout이나 외부 강제 종료는 이 절차와 별개다.

Celery는 `SIGTERM`으로 실행 중인 작업을 기다리는 warm shutdown을 수행한다. `SIGQUIT`의 cold shutdown과 `SIGKILL`은 작업 중단을 수반한다. 정상 종료 후 새 worker를 시작하는 것이 권장 재시작 방식이며, `SIGHUP`은 무중단 reload 보장으로 해석하지 않는다.

두 도구 모두 프로세스 관리자·컨테이너의 종료 유예 시간을 확보해야 한다. Q2는 내부 대기 작업까지 처리하므로 작업 한 건의 시간만으로 종료 유예 시간을 결정하지 않는다. 외부 I/O timeout과 내부 대기량을 제한하고 종료 절차를 실제 환경에서 검증해야 한다. 전원 차단·강제 종료에는 graceful shutdown을 기대할 수 없다. 운영 설명은 Linux 기준이며 Celery는 Windows를 공식 지원하지 않는다. Q2도 Windows에서는 timeout 등 OS별 차이가 있어 실제 검증이 필요하다.

근거: [Q2 종료 절차](https://django-q2.readthedocs.io/en/master/architecture.html#stop-procedure), [Celery 종료](https://docs.celeryq.dev/en/stable/userguide/workers.html#stopping-the-worker), [Celery 재시작](https://docs.celeryq.dev/en/stable/userguide/workers.html#restarting-the-worker), [Celery Windows 지원](https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows), [Q2 timeout](https://django-q2.readthedocs.io/en/master/configure.html#timeout).

## 이 프로젝트의 선택과 검증 범위

확정한 선택:

- Django Q2와 기존 PostgreSQL ORM broker를 사용한다. 별도 Redis는 추가하지 않는다.
- 기본 큐 하나, `qcluster` 실행 하나를 사용하고 내부 worker들이 메일·이미지 정리를 함께 처리한다.
- mail·media cluster 분리와 `ALT_CLUSTERS` 구성은 이번 범위에서 사용하지 않는다.
- 메일은 개발에서 실제 전송 없이 모의 처리하고 운영에서는 AWS SES로 전송한다.
- 이미지 교체·교육 삭제 시 정리를 Q2로 전환하되 rollback·공유 이미지 보호를 유지한다.
- 별도 DLQ는 보류하고 Q2의 실패 작업 확인·재등록 기능을 활용한다. 이 기능은 전용 broker DLQ와 구분한다.
- 신청 관리 CRUD는 후속 범위이며 이번에는 접수 상태 저장·표시만 다룬다.

worker 2개·timeout 60초·broker retry 300초·작은 내부 대기량으로 구성했다. 메일은 발송 기록으로 일반 일시 오류 5분/15분·일일 한도 24시간 대기·총 3회 제한을 적용하고 결과 불명은 재전송하지 않는다. 이미지는 작업별 ack_failure=False와 max_attempts=3을 사용한다. Django 이메일 API의 dev locmem/prod django-ses 선택·공유 전송 예산·실행 명령과 운영 전제는 [운영 가이드](guides/operations.md#백그라운드-worker와-자동-안내)를 따른다.

상담 안내 이메일 task는 `enqueue_consultation_reminder_emails`·`send_consultation_reminder_email`, 이미지 task는 `delete_unreferenced_education_image`다. Q2는 함수 경로를 스케줄·큐에 저장하므로 함수 이름 변경 시 코드와 영속 경로를 함께 전환해야 한다. 기존 큐를 기존 worker로 처리·정상 종료한 뒤 새 코드와 스케줄을 적용하는 절차와 과거 이미지 실패 재등록 방법은 [기존 task 경로 전환](guides/operations.md#기존-task-경로-전환)을 따른다.

신청·안내의 원자적 저장과 이미지 변경·ORM 큐의 같은 transaction 기록을 실제 PostgreSQL에서 검증했다. Q2 실패 목록은 등록되지 않은 작업을 복구하지 않으므로 메일은 영속 대상에서 재발견하고 이미지 큐 등록 실패는 DB 변경도 rollback한다. 이미지 작업의 참조 재검사와 메일의 원자적 처리권을 동시 실행·중복 작업으로 확인했다.

Windows에서 실제 qcluster subprocess의 run-once 정상 종료·결과 flush, 프로세스 트리 강제 종료 후 queued 복구/sending의 unknown 보존, 이미지 실패 후 재등록을 검증했다. 운영 SES는 실제 django-ses backend와 fake SDK로 검증하며 실제 AWS 연결·수신·Linux 서비스 관리자 종료 신호는 미검증이다. Windows의 강제 종료를 graceful shutdown 성공으로 간주하지 않는다. 실제 운영 한도는 [SES 발송 한도](https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html)를 따른다.
