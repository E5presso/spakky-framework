# ADR-0003: @task / @schedule 데코레이터 분리

- **상태**: Accepted
- **날짜**: 2026-03-15

## 맥락 (Context)

`spakky-task`의 초기 설계에서 `@task(background=True|False)` 데코레이터는 "백그라운드 디스패치"와 "동기 실행" 두 가지 실행 모드를 하나의 데코레이터에 담으려 했다. 그러나 구현 과정에서 다음 문제가 드러났다:

1. **모든 `@task` 메서드는 결국 태스크 큐로 디스패치된다.** `background=False`인 태스크가 "큐를 거치지 않고 직접 실행"되어야 한다면, 애초에 `@task`로 마크할 이유가 없다.
2. **정기 실행(periodic/batch) 태스크에 대한 요구가 별도로 존재한다.** 크론잡이나 일정 간격 실행은 "호출자가 디스패치"하는 `@task`와 근본적으로 다른 트리거 모델이다.
3. **하나의 데코레이터에 두 가지 관심사를 섞으면 DX가 나빠진다.** `background` 플래그의 의미가 직관적이지 않고, 스케줄 파라미터를 추가하면 시그니처가 비대해진다.

이에 따라 `@task`와 `@schedule`을 **상호 배타적인 두 개의 데코레이터**로 분리하는 설계를 검토했다.

## 결정 동인 (Decision Drivers)

- **단일 책임**: 각 데코레이터가 하나의 실행 모델만 표현
- **DX(개발자 경험)**: 데코레이터 시그니처만으로 의도 파악 가능
- **코어/플러그인 분리**: 스케줄 추상화는 코어(`spakky-task`)에, Celery Beat 바인딩은 플러그인(`spakky-celery`)에 배치
- **확장성**: 향후 다른 스케줄러 백엔드(APScheduler 등) 플러그인 추가 가능

## 고려한 대안 (Considered Options)

### 대안 A: `@task(background=True|False)` 유지, `schedule` 파라미터 추가

```python
@task(background=True, schedule=timedelta(minutes=30))
def health_check(self) -> None: ...
```

- 장점: 데코레이터 하나로 모든 경우 처리
- 단점: `background`와 `schedule`의 조합이 모호함 (`background=False, schedule=...`의 의미?), 파라미터 증가로 가독성 저하, 실행 모델이 섞여 aspect 구현 복잡화

### 대안 B: `@schedule` 데코레이터를 별도 플러그인(`spakky-celery`)에 배치

- 장점: 코어에 스케줄 개념 불필요
- 단점: 스케줄이 Celery에 종속, 다른 백엔드 플러그인에서 `@schedule` 재활용 불가, `spakky-task` TaskHandler 안에 코어에 없는 데코레이터가 섞이는 비대칭

### 대안 C: `@task` / `@schedule` 분리, 스케줄 추상화는 `spakky-task` 코어에 배치 ✅

```python
@task
def send_email(self, to: str) -> None: ...

@schedule(interval=timedelta(minutes=30))
def health_check(self) -> None: ...

@schedule(crontab=Crontab(hour=9, weekday=(0, 2, 4)))
def triweekly_report(self) -> None: ...
```

- 장점: 각 데코레이터가 단일 실행 모델, 코어에 스케줄 추상화가 있어 모든 플러그인이 공유, `Crontab` 값 객체로 Python 네이티브 타입 활용
- 단점: 코어에 `Crontab`, `ScheduleRoute` 추가로 코어 표면적 약간 증가

## 결정 (Decision)

**대안 C**를 채택한다.

### 핵심 구조

| 패키지          | 구성 요소                     | 역할                                                                                     |
| --------------- | ----------------------------- | ---------------------------------------------------------------------------------------- |
| `spakky-task`   | `@task` / `TaskRoute`         | 온디맨드 디스패치 마크                                                                   |
| `spakky-task`   | `@schedule` / `ScheduleRoute` | 정기 실행 스케줄 마크                                                                    |
| `spakky-task`   | `Crontab`                     | 크론 스케줄 값 객체                                                                      |
| `spakky-celery` | `CeleryTaskDispatchAspect`    | `@task` 메서드 호출을 `send_task()`로 변환                                               |
| `spakky-celery` | `CeleryPostProcessor`         | `@task`/`@schedule` 모두 Celery 태스크로 등록, `@schedule`은 추가로 `beat_schedule` 등록 |

### 설계 규칙

1. `@task`와 `@schedule`은 **조합 가능**하다. 하나의 메서드에 둘 다 적용하면:
   - Celery 태스크로 등록되고
   - `beat_schedule`에도 등록됨
   - 스케줄에 따라 자동 실행 + 수동 호출도 가능한 유스케이스
2. `@task` 메서드는 **호출 시점에 태스크 큐로 디스패치**된다 (aspect가 가로챔).
3. `@schedule` 메서드는 **호출자 없이 스케줄러가 주기적으로 실행**한다.
4. `ScheduleRoute`는 `interval`, `at`, `crontab` 중 정확히 하나만 가진다 (생성 시 검증).
5. `Crontab` 필드: `minute`, `hour`, `weekday`, `day`, `month` — `int | tuple[int, ...] | None` 타입.

## 결과 (Consequences)

### 긍정적

- `background` 플래그 제거로 `@task` 시그니처 단순화 (인자 없는 데코레이터)
- 데코레이터만으로 실행 모델(온디맨드 vs 정기) 즉시 식별 가능
- `Crontab` 값 객체가 코어에 있어 Celery 외 다른 스케줄러 플러그인에서도 재사용 가능
- Aspect pointcut이 단순해짐 (`TaskRoute.exists(x)`만 검사)

### 부정적

- 코어(`spakky-task`)의 퍼블릭 API 표면적이 `Crontab`, `ScheduleRoute`, `schedule` 3개 증가
- `@schedule` 메서드는 aspect가 가로채지 않으므로, 실수로 코드에서 직접 호출하면 로컬 실행됨 (의도된 동작이지만 혼동 가능)

### 중립적

- `TaskHandler` 스테레오타입은 `@task`와 `@schedule` 메서드를 모두 포함할 수 있음 — 핸들러 클래스 구조에 변화 없음
- `@task`+`@schedule` 조합 시 스케줄로도 실행되고 수동 호출로도 디스패치됨 (예: 일일 리포트를 자동 생성하지만 긴급 시 수동 트리거 가능)

## 참고 자료

- Spring `@Scheduled` 어노테이션: 온디맨드(`@Async`)와 정기(`@Scheduled`)를 별도 어노테이션으로 분리
- Celery `beat_schedule`: `celery.schedules.schedule`, `celery.schedules.crontab` 변환 매핑
- `spakky-task` 코드: `core/spakky-task/src/spakky/task/stereotype/`
- `spakky-celery` 코드: `plugins/spakky-celery/src/spakky/plugins/celery/post_processor.py`
