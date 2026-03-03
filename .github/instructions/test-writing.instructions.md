---
applyTo: "**/tests/**/*.py"
---

# 테스트 코드 규칙

이 규칙은 모든 테스트 파일에 자동 적용됩니다.

## 테스트 구조 (절대 규칙)

- **함수 기반만 허용**합니다. `class TestXxx`는 **절대 금지**입니다.
- 각 테스트 함수에 **docstring 필수**입니다.

## 네이밍 규칙

```
test_<대상함수>_<시나리오>_expect_<기대결과>
```

예시:
```python
def test_registry_register_entities_expect_all_registered(
    registry: ModelRegistry,
) -> None:
    """TableRegistrationPostProcessor가 @Table 어노테이션 클래스를 자동 등록하는지 검증한다."""
    ...
```

## 테스트 실행

- 에이전트는 **반드시 `execute/runTests` 도구를 사용**해야 합니다.
- 터미널에서 `pytest`, `uv run pytest`를 직접 실행하지 마세요.
- 테스트 파일 경로를 명시하여 불필요한 전체 실행을 피하세요.

## 모노레포 규칙

각 패키지의 테스트는 해당 패키지 디렉토리에서 실행해야 합니다.
루트에서 전체 실행하지 마세요.

## Fixture와 의존성

- `conftest.py`에 공통 fixture를 정의하세요.
- 테스트 간 상태 격리를 보장하세요 (특히 DB/Registry 관련).
- `scope="function"`을 기본으로 사용하세요.

## 커버리지 측정 워크플로우

커버리지 개선 작업 시 **반드시** 아래 순서를 따르세요:

### 1. 기존 테스트 구조 확인

테스트 추가 전에 **반드시** 해당 패키지의 테스트 구조를 확인하세요:

```bash
ls -la tests/  # unit/, integration/ 디렉토리 존재 여부 확인
```

많은 패키지가 `unit/`과 `integration/` 디렉토리로 분리되어 있습니다.
**기존 통합 테스트가 이미 해당 라인을 커버하고 있을 수 있습니다.**

### 2. 커버리지 측정 (전체 테스트)

커버리지는 **모든 테스트(unit + integration)**를 실행해서 측정해야 합니다:

```bash
# 올바른 방법: 패키지 전체 테스트
cd <package-dir> && uv run pytest --cov=spakky --cov-report=term-missing --cov-fail-under=0

# 잘못된 방법: unit 테스트만 실행
cd <package-dir> && uv run pytest tests/unit/ --cov=spakky  # ❌
```

### 3. 미커버 라인 분석

100% 미달성 시 **반드시** 분석하세요:

1. `pragma: no cover` 표시 여부 확인
2. 통합 테스트에서 이미 커버되는지 확인
3. 단위 테스트로 커버 가능한지 판단
4. 통합 테스트 필요 시 기존 통합 테스트 확장 고려

**100% 미달성 이유 분류:**

| 분류 | 예시 | 조치 |
|------|------|------|
| `pragma: no cover` | 에러 핸들링, TYPE_CHECKING | 의도적 제외, 추가 테스트 불필요 |
| 통합 테스트 필요 | 외부 시스템 콜백, 런타임 전용 | 통합 테스트 추가 또는 확장 |
| 테스트 누락 | 일반 분기, 조건문 | 단위 테스트 추가 |
| 동기/비동기 분리 | Sync consumer vs Async consumer | 양쪽 모두 테스트 필요 |

**주의:** 동기/비동기 버전이 별도로 존재하는 경우 (예: `KafkaEventConsumer` vs `AsyncKafkaEventConsumer`),
**양쪽 모두** 테스트해야 합니다. 통합 테스트가 한쪽만 커버할 수 있습니다.

### 4. 테스트 추가 후 즉시 검증

테스트 추가 후 **해당 파일**의 커버리지를 즉시 확인:

```bash
# 특정 파일 커버리지 확인
uv run pytest --cov=spakky.plugins.kafka.post_processor --cov-report=term-missing --cov-fail-under=0
```

**100% 달성 확인 후** 다음 파일로 이동하세요.

## Test-First Development (TDD)

새 기능/버그 수정 시 권장 워크플로우:

1. **실패하는 테스트 먼저 작성** — 재현/검증 테스트
2. **최소 구현**으로 테스트 통과시키기
3. **리팩터링** (테스트 통과 유지)

이 워크플로우가 불가능한 경우만 예외 (예: 설정 변경, 문서만 수정).

## Known Issue Marker (알려진 버그 문서화)

알려진 버그나 의도적으로 잘못된 동작을 테스트로 문서화할 때:

```python
import pytest

@pytest.mark.known_issue("설명: 왜 이 동작이 잘못되었는지")
def test_feature_incorrect_behavior_expect_wrong_result() -> None:
    """현재 잘못된 동작을 문서화하는 테스트.

    이 테스트는 '잘못된' 현재 동작을 검증합니다.
    버그가 수정되면 마커를 제거하고 기대값을 올바르게 변경하세요.
    """
    result = buggy_function()
    assert result == "wrong_but_current_behavior"
```

**마커 등록** (패키지의 `pyproject.toml`에 추가):

```toml
[tool.pytest.ini_options]
markers = [
    "known_issue(reason): 알려진 버그 - 테스트는 통과하지만 동작은 잘못됨",
]
```

**핵심 규칙:**
- `known_issue` 테스트도 **반드시 통과해야 함** — 마커는 동작이 잘못됨을 문서화할 뿐
- 마커 메시지는 간결하게, 복잡한 설명은 docstring에
- **버그 문서화**: 마커 추가 + 현재(잘못된) 동작 검증
- **버그 수정**: 마커 제거 + 올바른 기대값으로 변경
- **부분 수정**: 마커 유지, 설명만 업데이트
