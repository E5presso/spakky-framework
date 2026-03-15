---
applyTo: "**/tests/**/*.py"
---

# 테스트 코드 규칙

## 분류 기준

| 분류 | 위치 | 핵심 구분 |
|------|------|----------|
| **Unit** | `tests/unit/` | Mock/Fake, 격리 실행, ms 단위 |
| **Integration** | `tests/integration/` | testcontainers, 실제 인프라, BDD 시나리오 |

**잘못된 패턴**: `tests/integration/`에서 `task_always_eager=True` → Unit으로 이동

## 절대 규칙

- **함수 기반만**. `class TestXxx` 금지
- **docstring 필수**
- **네이밍**: `test_<대상>_<시나리오>_expect_<기대결과>`

## Fixture

- 공통 → `conftest.py`
- Unit: `scope="function"`
- Integration 컨테이너: `scope="package"` (비용 절감)

## 커버리지

`improve-coverage` 스킬 사용

## Known Issue

```python
@pytest.mark.known_issue("이유")
def test_buggy_behavior_expect_wrong_result() -> None: ...
```

