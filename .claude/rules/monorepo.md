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

```
spakky → spakky-domain → spakky-data ──┐
spakky → spakky-tracing ───────────────┤→ spakky-event → spakky-outbox (단방향)
spakky → spakky-task
spakky-logging → spakky (코어 유틸리티)
```

역방향 의존성을 추가하지 마세요.
