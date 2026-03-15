---
applyTo: "plugins/**/*.py"
---

# 플러그인 개발 규칙

## 구조

```
plugins/spakky-<name>/
├── src/spakky/plugins/<name>/
│   ├── __init__.py
│   └── main.py  ← initialize 함수 (엔트리 포인트)
├── tests/{unit,integration}/
└── pyproject.toml
```

## main.py 패턴

```python
from spakky.core.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    """Register Pods and Post-Processors for this plugin."""
    pass
```

## 의존성 방향

| 종류 | 최하위 의존 |
|------|-----------|
| UI (HTTP/CLI), 유틸리티 | `spakky` |
| 인프라 (ORM) | `spakky-data` |
| 트랜스포트 (MQ) | `spakky-event` |
| 태스크 브로커 (Celery) | `spakky-task` |

플러그인 → 다른 플러그인 직접 의존 **금지** (순환 의존 위험)

## Post-Processor 패턴

```python
from spakky.core.application.interfaces.post_processor import IApplicationContextPostProcessor
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.annotations.pod import Pod

@Pod()
class MyPostProcessor(IApplicationContextPostProcessor):
    def post_process(self, context: IApplicationContext) -> None: ...
```

## pyproject.toml 필수 항목

```toml
[project.entry-points."spakky.plugins"]
spakky-<name> = "spakky.plugins.<name>.main:initialize"

[tool.pytest.ini_options]
markers = ["known_issue(reason): 알려진 버그"]
```

## 금지 사항

- `__init__.py`에 공개 API 직접 노출 금지 — 명시적 import 경로 사용
- `initialize`에서 동기 I/O 금지
- 다른 플러그인 직접 import 금지

