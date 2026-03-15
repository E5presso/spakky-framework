---
applyTo: "**/pyproject.toml"
---

# Monorepo 구조 규칙

이 규칙은 pyproject.toml 파일 작업 시 자동 적용됩니다.

## Pre-commit 도구 실행 원칙

**모든 pre-commit 도구(pyrefly, ruff 등)는 패키지 디렉토리 내에서 실행하는 것이 원칙.**

각 패키지가 독립적인 `tests/` 디렉토리와 설정을 가지므로, 루트에서 도구 실행 시 모듈 충돌 또는 설정 불일치 발생.

**올바른 사용:**
- **Pre-commit 워크플로우**: 자동으로 각 패키지 디렉토리에서 실행 (정상 동작)
- **수동 실행**: 해당 패키지로 이동 후 실행
  ```bash
  cd core/spakky && uv run pyrefly check
  cd core/spakky && uv run ruff check .
  cd core/spakky && uv run pytest
  ```

**금지:**
- 루트에서 `uv run pyrefly check`, `uv run ruff check`, `uv run pytest` 등 직접 실행
- 루트 `pyproject.toml`의 도구 설정 수정 (scripts/ 전용)

## 패키지 의존성 방향

```
spakky → spakky-domain → spakky-data → spakky-event → spakky-task (단방향)
spakky-logging → spakky (코어 유틸리티)
```

역방향 의존성을 추가하지 마세요.
