# spakky-logging

Spakky Framework를 위한 구조화 로깅 시스템입니다. contextvars 기반 로그 컨텍스트 전파, 설정 가능한 formatter(Text, JSON, Pretty), AOP 기반 메서드 호출 로깅, PostProcessor 기반 자동 설정을 제공합니다.

## 설치

```bash
pip install spakky-logging
```

## 빠른 시작

### 1. 플러그인 자동 등록

`spakky-logging`은 `load_plugins()`를 통해 자동으로 로드됩니다.

```python
app = SpakkyApplication(ApplicationContext()).load_plugins().scan(my_app).start()
```

### 2. `@logged`로 메서드 표시

```python
from spakky.plugins.logging import logged

class UserService:
    @logged()
    async def create_user(self, name: str, password: str) -> User:
        ...
```

### 3. 설정(선택)

`LoggingConfig`로 기본값을 override합니다.

`LoggingConfig`는 `@Configuration` Pod로 로드되며, `pydantic-settings`를 통해
`SPAKKY_LOGGING__*` 환경변수를 읽습니다.

```bash
export SPAKKY_LOGGING__LEVEL=10
export SPAKKY_LOGGING__FORMAT=json
export SPAKKY_LOGGING__MASK_KEYS='["password", "token", "secret"]'
export SPAKKY_LOGGING__SLOW_THRESHOLD_MS=500
```

### 4. LogContext 전파

모든 log record에 자동 포함될 contextual key-value pair를 바인딩합니다.

```python
from spakky.plugins.logging import LogContext

LogContext.bind(request_id="req-123", user_id="u-456")

with LogContext.scope(trace_id="t-789"):
    # 이 block 안의 모든 log는 trace_id를 포함
    ...
```

## 주요 기능

| 기능                     | 설명                                                |
| --------------------------- | ---------------------------------------------------------- |
| `@logged()` annotation      | AOP 기반 method call/result/error 자동 logging       |
| `LogContext`                | contextvars 기반 structured context 전파           |
| `ContextInjectingFilter`    | 모든 `LogRecord`에 LogContext value 주입           |
| `SpakkyTextFormatter`       | pipe로 구분된 text format                                 |
| `SpakkyJsonFormatter`       | line당 JSON object 하나                                   |
| `SpakkyPrettyFormatter`     | 개발용 ANSI color multi-column format           |
| `LoggingConfig`             | 중앙 logging configuration용 `@Configuration` pod |
| `LoggingSetupPostProcessor` | application start 시 root logger 자동 설정           |
| 민감 데이터 masking      | log output에서 `password`, `token`, `secret` 등을 masking |
| 느린 호출 감지         | method 실행 시간이 threshold를 넘으면 warning 출력 |
| 결과 truncation           | 긴 return value를 log output에서 잘라냄 |

## 라이선스

MIT License
