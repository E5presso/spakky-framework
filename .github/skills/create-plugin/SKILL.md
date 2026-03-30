---
name: create-plugin
description: Scaffold a new Spakky Framework plugin package from scratch. Use this skill when asked to create, add, or implement a new plugin under the plugins/ directory.
---

# 플러그인 생성 워크플로우

## Step 1: 스캐폴딩

```bash
uv run python scripts/create_package.py plugin spakky-<name> --description "<설명>"
```

이 스크립트가 자동 처리하는 항목:
- 디렉터리 구조 생성 (`src/`, `tests/`, `.vscode/`)
- `pyproject.toml` (엔트리 포인트, 빌드, 린터, 테스트, 커버리지 설정)
- 워크스페이스 멤버 등록 (루트 `pyproject.toml`)
- commitizen `version_files` 등록
- `uv.sources` 등록
- `.pre-commit-config.yaml`
- `README.md`, `CHANGELOG.md`
- `main.py` (initialize 함수 스텁)
- `uv sync --all-packages --all-extras`

## Step 2: 구현

스캐폴딩 후 실제 플러그인 로직을 구현합니다.

### 의존성 체인

| 플러그인 종류 | 의존 체인 |
|------------|---------|
| UI (HTTP/CLI) | `spakky` 코어만 |
| 유틸리티 | `spakky` 코어만 |
| 인프라 (DB/ORM) | `spakky-data`까지 |
| 트랜스포트 (MQ/브로커) | `spakky-event`까지 |

**핵심 의존 방향**: `spakky` → `spakky-domain` → `spakky-data` → `spakky-event` (단방향)
`spakky` → `spakky-tracing` → `spakky-event` (트레이싱 경로)

### 코어 패키지도 동일

```bash
uv run python scripts/create_package.py core spakky-<name> --description "<설명>"
```
