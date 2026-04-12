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
spakky → spakky-task                   │
spakky → spakky-saga ─────────────────-┘
spakky-logging → spakky (코어 유틸리티)
```

- 역방향 의존성 추가 금지.
- 플러그인 → 다른 플러그인 직접 import 금지.
