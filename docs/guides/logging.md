# 구조화 로깅

`spakky-logging`은 `@logged()` 데코레이터로 메서드 호출을 자동 로깅하고, `LogContext`로 컨텍스트를 전파합니다.

---

## 동작 원리

1. `@logged()` 어노테이션이 붙은 메서드를 `LoggingAspect` / `AsyncLoggingAspect`가 감지
2. 메서드 호출 시 인자, 반환값, 실행 시간을 자동 기록
3. `LogContext`에 바인딩된 값이 모든 로그 레코드에 자동 주입

---

## 설정

`LoggingConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.plugins.logging
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.logging.PLUGIN_NAME})
    .scan(apps)
    .start()
)
```

환경변수 예시:

```bash
export SPAKKY_LOGGING__LEVEL=20          # logging.INFO
export SPAKKY_LOGGING__FORMAT=json       # text | json | pretty
export SPAKKY_LOGGING__DATE_FORMAT="%Y-%m-%dT%H:%M:%S%z"
export SPAKKY_LOGGING__SLOW_THRESHOLD_MS=1000.0
export SPAKKY_LOGGING__MAX_RESULT_LENGTH=200
```

| 필드 | 환경변수 | 기본값 |
|------|---------|--------|
| `level` | `SPAKKY_LOGGING__LEVEL` | `logging.INFO` (20) |
| `format` | `SPAKKY_LOGGING__FORMAT` | `LogFormat.TEXT` |
| `date_format` | `SPAKKY_LOGGING__DATE_FORMAT` | `"%Y-%m-%dT%H:%M:%S%z"` |
| `mask_keys` | `SPAKKY_LOGGING__MASK_KEYS` | `["password", "secret", "token", "key"]` |
| `mask_replacement` | `SPAKKY_LOGGING__MASK_REPLACEMENT` | `"******"` |
| `slow_threshold_ms` | `SPAKKY_LOGGING__SLOW_THRESHOLD_MS` | `1000.0` |
| `max_result_length` | `SPAKKY_LOGGING__MAX_RESULT_LENGTH` | `200` |

---

## @logged 데코레이터

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.logging import logged

@Pod()
class UserService:
    @logged()
    def create_user(self, name: str, email: str) -> str:
        return f"user_{name}"

    @logged(enable_masking=True, masking_keys=["email"])
    def update_email(self, user_id: str, email: str) -> None:
        ...

    @logged(log_args=False, log_result=False)
    def internal_process(self) -> None:
        """인자와 반환값을 로그에 포함하지 않음"""
        ...
```

### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `enable_masking` | `bool` | `True` | 민감 데이터 마스킹 활성화 |
| `masking_keys` | `list[str] \| None` | `None` | 마스킹 대상 키 (None이면 글로벌 설정 사용) |
| `slow_threshold_ms` | `float \| None` | `None` | 느린 호출 경고 임계값 (None이면 글로벌 설정 사용) |
| `max_result_length` | `int \| None` | `None` | 반환값 repr 최대 길이 (None이면 글로벌 설정 사용) |
| `log_args` | `bool` | `True` | 인자를 로그에 포함할지 여부 |
| `log_result` | `bool` | `True` | 반환값을 로그에 포함할지 여부 |

---

## LogContext

`contextvars` 기반 컨텍스트 전파로, 요청 ID 등 공통 정보를 모든 로그에 자동 주입합니다.

```python
from spakky.plugins.logging import LogContext

# 바인딩
LogContext.bind(request_id="abc-123", user_id="user-42")

# 조회
context = LogContext.get()  # {"request_id": "abc-123", "user_id": "user-42"}

# 언바인딩
LogContext.unbind("user_id")

# 전체 초기화
LogContext.clear()
```

### scope 컨텍스트 매니저

`with` 블록 내에서만 값을 바인딩하고, 블록 종료 시 이전 상태로 복원합니다.

```python
from spakky.plugins.logging import LogContext

LogContext.bind(request_id="abc-123")

with LogContext.scope(operation="create_order", order_id="ord-1"):
    # 이 블록 내에서는 request_id, operation, order_id 모두 사용 가능
    ...

# 블록 종료 후 operation, order_id는 사라지고 request_id만 남음
```

---

## 출력 포맷

`LogFormat` 열거형으로 3가지 포맷을 지원합니다.

| 포맷 | 클래스 | 용도 |
|------|--------|------|
| `TEXT` | `SpakkyTextFormatter` | 프로덕션 텍스트 로그 |
| `JSON` | `SpakkyJsonFormatter` | 구조화 로그 수집기 (ELK, Loki 등) |
| `PRETTY` | `SpakkyPrettyFormatter` | 로컬 개발 (컬러 출력) |

---

## 패키지별 로그 레벨

`package_levels` 설정으로 특정 로거의 레벨을 개별 제어할 수 있습니다.

```bash
export SPAKKY_LOGGING__PACKAGE_LEVELS__sqlalchemy.engine=20
export SPAKKY_LOGGING__PACKAGE_LEVELS__uvicorn=30
```

---

## 분산 트레이싱 연동

`spakky-opentelemetry` 플러그인이 함께 로드되면, `LogContextBridge`가 `TraceContext`의 trace/span ID를 `LogContext`에 자동 동기화합니다. 별도 설정 없이 로그에 트레이스 ID가 포함됩니다.
