---
name: update-dependencies
description: Update all external dependency versions to latest across the monorepo. Use this skill when asked to upgrade, update, or refresh dependency versions.
---

# 의존성 최신화 워크플로우

아래 단계를 **순서대로** 수행하세요.

## Step 1: 외부 의존성 수집

모든 `pyproject.toml`에서 **외부 의존성**(워크스페이스 멤버 제외)을 추출합니다.

```bash
# 워크스페이스 멤버 이름 확인
uv run python -c "
import tomllib
from pathlib import Path
root = tomllib.loads(Path('pyproject.toml').read_text())
members = root.get('tool', {}).get('uv', {}).get('workspace', {}).get('members', [])
for m in members:
    for p in Path('.').glob(m):
        pkg = tomllib.loads((p / 'pyproject.toml').read_text())
        print(pkg['project']['name'])
"
```

각 `pyproject.toml`의 `[project] dependencies`, `[project.optional-dependencies]`, `[dependency-groups]`에서 외부 패키지명과 현재 버전 제약을 수집하세요.

**제외 대상**: 워크스페이스 멤버 간 의존성 (`spakky`, `spakky-domain`, `spakky-data`, `spakky-event` 등)

## Step 2: 최신 버전 확인

각 외부 패키지의 PyPI 최신 버전을 확인합니다:

```bash
uv pip index versions <package-name>
```

> **주의**: `uv_build` 같은 빌드 시스템 패키지도 포함하세요 (`[build-system] requires`).

## Step 3: pyproject.toml 업데이트

버전 제약을 최신 버전 기준으로 갱신합니다.

**갱신 규칙**:
- `>=X.Y.Z` → 최신 버전으로 하한 갱신 (예: `>=2.0.45` → `>=2.0.48`)
- 상한 제약(`<X.0.0`)이 있으면 최신 버전이 포함되도록 조정
- 이미 최신이면 건너뛰기
- 워크스페이스 내부 의존성은 **절대로 수정하지 않음**

## Step 4: 락파일 갱신 및 설치

```bash
uv lock --upgrade
uv sync --all-packages --all-extras
```

## Step 5: 전체 테스트 실행

```bash
uv run python scripts/run_coverage.py --with-integration
```

**전체 패키지가 통과해야** 다음 단계로 진행합니다.

## Step 6: 호환성 이슈 마이그레이션

테스트 실패 시:

1. 에러 메시지에서 **breaking change** 식별 (import 경로 변경, API 제거 등)
2. 해당 라이브러리의 변경 로그 또는 마이그레이션 가이드 참조
3. 소스 코드 수정 적용
4. **Step 5로 돌아가** 전체 테스트 재실행

> 실패-수정-재실행 루프를 전체 통과할 때까지 반복하세요.
