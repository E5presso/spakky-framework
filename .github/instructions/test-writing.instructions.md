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

- 에이전트는 **반드시 `runTests` 도구를 사용**해야 합니다.
- 터미널에서 `pytest`, `uv run pytest`를 직접 실행하지 마세요.
- 테스트 파일 경로를 명시하여 불필요한 전체 실행을 피하세요.

## 모노레포 규칙

각 패키지의 테스트는 해당 패키지 디렉토리에서 실행해야 합니다.
루트에서 전체 실행하지 마세요.

## Fixture와 의존성

- `conftest.py`에 공통 fixture를 정의하세요.
- 테스트 간 상태 격리를 보장하세요 (특히 DB/Registry 관련).
- `scope="function"`을 기본으로 사용하세요.
