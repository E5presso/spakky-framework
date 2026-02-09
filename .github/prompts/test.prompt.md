---
name: test
description: Spakky Framework 테스트 작성 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - edit/editFiles
  - edit/createFile
  - search
  - search/listDirectory
  - execute/runTests
  - execute/testFailure
  - read/problems
  - search/usages
  - todo
---

# 테스트 작성 워크플로우

## Step 1: 기존 패턴 확인

1. 대상 패키지의 기존 테스트 파일을 검색하세요.
2. fixture 구조(`conftest.py`)를 파악하세요.
3. 동일 패키지 내 테스트 네이밍 패턴을 확인하세요.

## Step 2: 테스트 작성

### 절대 규칙

- **함수 기반만** 허용. `class TestXxx` 절대 금지.
- 네이밍: `test_<대상함수>_<시나리오>_expect_<기대결과>`
- 각 테스트 함수에 **docstring 필수**.
- 반환 타입은 `-> None`으로 명시.

### 예시

```python
def test_registry_register_entities_expect_all_registered(
    registry: ModelRegistry,
) -> None:
    """TableRegistrationPostProcessor가 @Table 어노테이션 클래스를 자동 등록하는지 검증한다."""
    assert registry.is_registered(User)
```

## Step 3: 실행

- **반드시 `execute/runTests` 도구를 사용**하세요.
- 터미널에서 `pytest`나 `uv run pytest`를 직접 실행하지 마세요.
- 테스트 파일 경로를 명시하세요.

## Step 4: 검증

1. 모든 테스트 통과 확인.
2. `Any` 타입 사용 여부 확인.
3. fixture scope 적절성 확인 (기본: `function`).

테스트 대상: ${input:target:테스트할 대상을 설명하세요}
