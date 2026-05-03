---
name: check
description: 변경된 패키지별로 lint(ruff) + 타입 체크(pyrefly) + 테스트(pytest) + 레이어 의존 방향 검증을 실행합니다.
argument-hint: "[package-name]"
user-invocable: true
---

# Check

코드 변경 후 품질 검증을 한 번에 수행합니다.

## 대상 패키지 결정

- 인자가 있으면 해당 패키지만 검증한다.
- 인자가 없으면 `git diff --name-only`로 변경된 파일에서 패키지를 자동 감지한다.
- 여러 패키지가 변경되었으면 **병렬 서브에이전트**로 패키지별 검증한다.

## 실행 순서

1. **포맷팅** — `uv run ruff format .` (패키지 디렉토리 내에서, 커밋 전 hook 실패 방지)
2. **Python 하네스 규칙 검증** — `uv run python ../../.agents/skills/check/scripts/validate_python_harness.py .` (패키지 디렉토리 내에서, root pre-commit도 전체 실행)
3. **레이어 의존 방향 검증** — 패키지 간 역방향 import가 없는지 확인.
4. **Lint** — `uv run ruff check .` (패키지 디렉토리 내에서)
5. **타입 체크** — `uv run pyrefly check` (패키지 디렉토리 내에서)
6. **테스트** — `uv run pytest` (패키지 디렉토리 내에서)

## 1. Python 하네스 규칙 검증

pyrefly/ruff가 의미 규칙으로 잡지 못하는 금지 패턴을 AST 기반으로 검사한다.

```bash
cd <package-dir> && uv run python ../../.agents/skills/check/scripts/validate_python_harness.py .
```

현재 차단 항목:

- `typing.Protocol` / `typing_extensions.Protocol` import
- `Protocol` 상속 및 `@runtime_checkable` 구조 타이핑
- 순수 인터페이스 역할의 `Abstract*` 네이밍 (`I*` 접두사로 수정)
- `src/` 내 `TypeError` / `ValueError` 직접 `raise`
- `src/` 내 `assert`
- `tests/` 내 `class Test*` 클래스 기반 테스트
- `src/` 내 `getattr()` / `hasattr()` / `setattr()` 사유 없는 동적 attribute 접근
- `type: ignore` / `pyrefly: ignore` / `pragma: no cover` / `pragma: no branch` 사유 없는 opt-out 주석
- 플러그인에서 다른 플러그인 직접 import
- 도메인 레이어에서 인프라 패키지 import
- 에러 파일의 `__str__` 오버라이드

위반이 있으면 타입 체크 실행 전에 수정한다.

루트 pre-commit은 패키지별 hook이 없는 신규 패키지까지 잡기 위해 같은 검사를 전체 범위로 항상 실행한다.

## 2. 레이어 의존 방향 검증

AGENTS.md에 정의된 의존 방향(monorepo.md 참조)을 검증한다.

역방향 의존이 발생하는 패턴을 grep으로 검사한다:

```bash
# 예: spakky-domain이 spakky-data를 import하면 역방향 위반
grep -rn "from spakky.core.data\|from spakky.data\|import spakky.data" core/spakky-domain/src/
# 예: spakky-event가 spakky-outbox를 import하면 역방향 위반
grep -rn "from spakky.outbox\|import spakky.outbox" core/spakky-event/src/
```

변경된 패키지의 의존 방향만 검사한다. 위반이 있으면 파일과 라인을 출력하고 수정.

## 3. Lint

```bash
cd <package-dir> && uv run ruff check .
```

- 실패 시 → `uv run ruff check --fix .`로 자동 수정 가능한 것은 수정.
- 자동 수정 불가능한 것은 수동 수정 후 재실행.

## 4. 타입 체크

```bash
cd <package-dir> && uv run pyrefly check
```

- 실패 시 → 테스트 실행하지 않고 타입 오류부터 수정 후 재실행.
- opt-out 주석은 최후 수단. 사유 필수: `# pyrefly: ignore - 사유`

## 5. 테스트 & 커버리지

```bash
cd <package-dir> && uv run pytest
```

- 실패 시 → 원인 분석 후 수정하고 재실행.
- **커버리지 100% 필수** — 변경된 코드의 커버리지가 100%여야 한다. 미달 시 테스트를 추가한다.

### 커버리지 측정

**반드시 `scripts/run_coverage.py`를 사용한다.**

```bash
# 단일 패키지
uv run python scripts/run_coverage.py --package <package-name>
# 전체 (병렬)
uv run python scripts/run_coverage.py
```

| 금지 | 이유 |
|------|------|
| `cd <dir> && uv run pytest --cov` | pyproject.toml 설정 무시 |
| `pytest --cov` 직접 실행 | 경로 설정 오류 가능 |

> 커버리지 **개선**이 필요하면 → `/improve-coverage`

## 규칙

- 여섯 단계 모두 통과해야 완료 (포맷팅 + Python 하네스 + 레이어 + 린트 + 타입 + 테스트/커버리지).
- Python 하네스 위반 > 레이어 위반 > 린트 오류 > 타입 오류 > 테스트 실패 > 커버리지 미달 순으로 우선순위.
- **루트에서 직접 실행 금지** — 반드시 패키지 디렉토리 내에서 실행.
- 여러 패키지를 검증할 때는 병렬 서브에이전트 활용.

$ARGUMENTS
