---
name: create-plugin
description: Scaffold a new Spakky Framework plugin package from scratch. Use this skill when asked to create, add, or implement a new plugin under the plugins/ directory.
---

# 플러그인 생성 워크플로우

아래 단계를 **순서대로** 수행하세요.

## Step 1: 의존성 체인 파악

플러그인이 의존해야 하는 코어 체인을 결정합니다:

| 플러그인 종류 | 의존 체인 |
|------------|---------|
| UI (HTTP/CLI) | `spakky` 코어만 |
| 유틸리티 | `spakky` 코어만 |
| 인프라 (DB/ORM) | `spakky-data`까지 |
| 트랜스포트 (MQ/브로커) | `spakky-event`까지 |

**핵심 의존 방향**: `spakky` → `spakky-domain` → `spakky-data` → `spakky-event` (단방향)

## Step 2: 패키지 생성

```bash
# 워크스페이스 루트에서 실행
cd plugins
uv init --lib spakky-<name>
cd spakky-<name>

# 올바른 패키지 구조 생성
mkdir -p src/spakky/plugins/<name>
touch src/spakky/plugins/<name>/__init__.py
touch src/spakky/plugins/<name>/main.py
```

## Step 3: 워크스페이스 등록

루트 `pyproject.toml`의 `[tool.uv.workspace]` members에 추가:

```toml
[tool.uv.workspace]
members = [
  # ... 기존 패키지 ...
  "plugins/spakky-<name>",
]
```

## Step 4: 플러그인 pyproject.toml 설정

플러그인의 `pyproject.toml`에 엔트리 포인트 추가:

```toml
[project.entry-points."spakky.plugins"]
spakky-<name> = "spakky.plugins.<name>.main:initialize"
```

## Step 5: initialize 함수 구현

`main.py`에 초기화 함수를 구현합니다:

```python
from spakky.core.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    """Register your Pods and Post-Processors here."""
    pass
```

## Step 6: 버전 동기화 설정

루트 `pyproject.toml`의 `[tool.commitizen]` version_files에 추가:

```toml
[tool.commitizen]
version_files = [
  # ... 기존 패키지 ...
  "plugins/spakky-<name>/pyproject.toml:version",
]
```

## Step 7: pre-commit 설정 복사

기존 플러그인(예: `plugins/spakky-fastapi`)의 `.pre-commit-config.yaml`을 참고하여
새 플러그인의 `.pre-commit-config.yaml`을 작성하세요.

## Step 8: 테스트 구조 생성

```bash
mkdir -p tests/unit tests/integration
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

## Step 9: 의존성 설치 및 검증

```bash
# 루트에서 전체 동기화
cd ../..
uv sync --all-packages --all-extras

# 플러그인에서 테스트 실행
cd plugins/spakky-<name>
uv run pytest
```
