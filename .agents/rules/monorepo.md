---
paths:
  - "**/pyproject.toml"
---

# Monorepo 구조 규칙

## Pre-commit 도구 실행 원칙

모든 pre-commit 도구(pyrefly, ruff 등)는 **패키지 디렉토리 내에서** 실행:

```bash
cd core/spakky && uv run pyrefly check
cd core/spakky && uv run ruff check .
cd core/spakky && uv run pytest
```

**금지**: 루트에서 `uv run pyrefly check`, `uv run ruff check`, `uv run pytest` 직접 실행

## 패키지 의존성 방향

패키지 목록과 버전/외부 의존은 각 package `pyproject.toml`이 SSOT다. 아래는 허용 방향 매트릭스다.

| 대상 | 허용되는 workspace runtime 의존 | 금지 |
|------|--------------------------------|------|
| `spakky` | 없음 (`optional-dependencies`는 설치 편의만 허용) | core 확장/플러그인 source import |
| `spakky-domain`, `spakky-tracing`, `spakky-task`, `spakky-auth`, `spakky-actuator`, `spakky-cache`, `spakky-agent` | `spakky` | 다른 core 확장 역방향 의존, plugin 의존 |
| `spakky-data` | `spakky-domain` | infra/plugin 의존 |
| `spakky-event` | `spakky-domain`, `spakky-data`, `spakky-tracing` | outbox/saga/plugin 의존 |
| `spakky-outbox` | `spakky-event`, `spakky-tracing` | saga/plugin 의존 |
| `spakky-saga` | `spakky`, `spakky-domain`, `spakky-auth` | event/outbox/plugin 의존 |
| `plugins/*` | 필요한 core 패키지 + 외부 SDK | 다른 plugin의 `src/` 직접 import, core로의 역방향 import |

예외: plugin 간 optional/dev 의존은 통합 테스트나 contribution entry-point 연결에 한해 허용하지만, `src/` 코드에서 다른 plugin module을 직접 import하면 위반이다.

공통 금지:
- matrix 역방향 workspace 의존 추가 금지.
- 도메인 레이어는 인프라 패키지를 import하지 않는다.
