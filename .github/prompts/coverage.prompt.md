---
name: coverage
description: Spakky Framework 커버리지 개선 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - edit/editFiles
  - edit/createFile
  - search
  - search/listDirectory
  - execute/runTests
  - execute/runInTerminal
  - execute/getTerminalOutput
  - search/usages
  - todo
---

# 커버리지 개선 워크플로우

아래 단계를 **반드시 순서대로** 수행하세요.

## Step 1: 기존 테스트 구조 확인

```bash
ls -la tests/
# unit/, integration/ 디렉토리 존재 여부 확인
```

많은 패키지가 `unit/`과 `integration/` 디렉토리로 분리되어 있습니다.
**기존 통합 테스트가 이미 해당 라인을 커버하고 있을 수 있습니다.**

## Step 2: 전체 테스트로 커버리지 측정

커버리지는 **모든 테스트(unit + integration)**를 실행해서 측정해야 합니다:

```bash
# 올바른 방법: 패키지 전체 테스트
cd <package-dir> && uv run pytest --cov=spakky --cov-report=term-missing --cov-fail-under=0
```

> ❌ **금지**: `tests/unit/` 또는 `tests/integration/`만 실행하는 것

## Step 3: 미커버 라인 분류

100% 미달성 시 각 라인을 아래 기준으로 분류합니다:

| 분류 | 예시 | 조치 |
|------|------|------|
| `pragma: no cover` | 에러 핸들링, `TYPE_CHECKING` 블록 | 의도적 제외 — 추가 테스트 불필요 |
| 통합 테스트 필요 | 외부 시스템 콜백, 런타임 전용 브로커 경로 | 통합 테스트 추가/확장 |
| 테스트 누락 | 일반 분기, 조건문 | 단위 테스트 추가 |
| 동기/비동기 분리 | `KafkaEventConsumer` vs `AsyncKafkaEventConsumer` | **양쪽 모두** 테스트 필요 |

## Step 4: 파일별 100% 달성

각 파일마다:

1. 단위 테스트로 커버 가능한 라인 → 단위 테스트 추가
2. 통합 테스트 필요 라인 → 기존 통합 테스트 확장 고려
3. 커버 불가 라인 → `# pragma: no cover` 표시 (사유 명시)

```bash
# 특정 파일 커버리지 즉시 검증
uv run pytest --cov=spakky.<module.path> --cov-report=term-missing --cov-fail-under=0
```

**100% 달성 확인 후** 다음 파일로 이동하세요.

## Step 5: 테스트 스타일 규칙

- **함수 기반만** 허용 (`class TestXxx` 금지)
- 네이밍: `test_<대상함수>_<시나리오>_expect_<기대결과>`
- 각 테스트 함수에 **docstring 필수**
- `scope="function"` fixture 기본

## Step 6: 최종 검증

```bash
cd <package-dir> && uv run pytest --cov=spakky --cov-report=term-missing
```

100% 미달성 이유를 명시적으로 보고하세요.

커버리지 개선 대상 패키지: ${input:package:패키지 경로 (예: core/spakky, plugins/spakky-fastapi)}
