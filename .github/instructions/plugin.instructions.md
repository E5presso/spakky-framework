---
applyTo: "plugins/**/*.py"
---

# 플러그인 개발 규칙

이 규칙은 `plugins/` 경로 하위 모든 Python 파일에 자동 적용됩니다.

## 플러그인 구조

```
plugins/spakky-<name>/
├── src/spakky/plugins/<name>/
│   ├── __init__.py
│   └── main.py          ← 엔트리 포인트 (initialize 함수)
├── tests/
│   ├── unit/
│   └── integration/
└── pyproject.toml
```

## main.py 패턴

모든 플러그인은 `initialize` 함수를 엔트리 포인트로 노출합니다:

```python
from spakky.core.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    """Register Pods and Post-Processors for this plugin.

    Args:
        app: The Spakky application instance.
    """
    pass
```

## 의존성 방향 규칙

플러그인은 코어 체인의 **한 계층만** 최하위 의존으로 가져야 합니다:

| 플러그인 종류 | 의존 허용 범위 | 예시 |
|------------|-------------|------|
| UI (HTTP, CLI) | `spakky` 코어까지 | `spakky-fastapi`, `spakky-typer` |
| 유틸리티 | `spakky` 코어까지 | `spakky-security` |
| 인프라 (ORM) | `spakky-data`까지 | `spakky-sqlalchemy` |
| 트랜스포트 (MQ) | `spakky-event`까지 | `spakky-rabbitmq`, `spakky-kafka` |

**금지**: 플러그인이 다른 플러그인에 직접 의존하는 것 (순환 의존 위험)

## 설정 클래스 패턴

플러그인 설정은 `@Pod()` 또는 `@Configuration`으로 등록합니다:

```python
from dataclasses import dataclass
from spakky.core.pod.annotations.pod import Pod

@Pod()
@dataclass
class KafkaConfig:
    """Configuration for Kafka connection."""

    bootstrap_servers: str
    group_id: str
```

## Post-Processor 패턴

플러그인이 컨테이너 스캔 후 추가 처리가 필요한 경우 Post-Processor를 등록합니다:

```python
from spakky.core.application.interfaces.post_processor import IApplicationContextPostProcessor
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.annotations.pod import Pod

@Pod()
class MyPostProcessor(IApplicationContextPostProcessor):
    """Post-processor for registering ..."""

    def post_process(self, context: IApplicationContext) -> None:
        """Process the application context after scanning.

        Args:
            context: The application context.
        """
        pass
```

## 테스트 구조

- `tests/unit/` — 외부 의존성 없는 순수 단위 테스트
- `tests/integration/` — 외부 시스템 (Docker, 실제 브로커 등) 의존 테스트
- `tests/apps/` — 통합 테스트용 샘플 앱 코드 (있는 경우)
- `tests/conftest.py` — 공통 fixture

## pyproject.toml 체크리스트

새 플러그인의 `pyproject.toml`에 반드시 포함해야 하는 항목:

```toml
[project.entry-points."spakky.plugins"]
spakky-<name> = "spakky.plugins.<name>.main:initialize"

[tool.pytest.ini_options]
markers = [
    "known_issue(reason): 알려진 버그 - 테스트는 통과하지만 동작은 잘못됨",
]
```

## 금지 사항

- 플러그인 `__init__.py`에 공개 API를 직접 노출하지 마세요 — 사용자는 명시적 import 경로를 사용
- `initialize` 함수에서 동기 I/O 작업 수행 금지
- 다른 플러그인 패키지를 직접 import 금지
