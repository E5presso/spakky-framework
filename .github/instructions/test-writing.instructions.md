---
applyTo: "**/tests/**/*.py"
---

# 테스트 코드 규칙

## 구조 (절대 규칙)

- **함수 기반만** 허용. `class TestXxx` **금지**.
- 각 테스트 함수에 **docstring 필수**.

> **기술 부채**: 일부 레거시 테스트 파일(8개)에 클래스 기반 테스트가 존재합니다.
> 해당 파일 수정 시 함수 기반으로 마이그레이션을 고려하세요.

## 네이밍

```
test_<대상함수>_<시나리오>_expect_<기대결과>
```

예시:
```python
def test_registry_register_entities_expect_all_registered(registry: ModelRegistry) -> None:
    """TableRegistrationPostProcessor가 @Table 어노테이션 클래스를 자동 등록하는지 검증한다."""
```

## 테스트 실행

- `execute/runTests` 도구 사용 (터미널 직접 실행 금지)
- 각 패키지 디렉토리에서 실행 (`cd <package-dir>`)
- 파일 경로를 명시해 불필요한 전체 실행 방지

## Fixture 규칙

- 공통 fixture → `conftest.py`
- `scope="function"` 기본 (테스트 간 상태 격리)

## 커버리지

커버리지 개선은 **`improve-coverage` 스킬** 사용. 미커버 라인 분류:

| 분류 | 조치 |
|------|------|
| `pragma: no cover` | 의도적 제외 — 추가 불필요 |
| 통합 테스트 필요 | 통합 테스트 추가/확장 |
| 테스트 누락 | 단위 테스트 추가 |
| 동기/비동기 분리 | 양쪽 모두 테스트 필요 |

## TDD

1. 실패하는 테스트 먼저 작성
2. 최소 구현으로 통과
3. 리팩터링 (통과 유지)

## Known Issue Marker

알려진 버그를 테스트로 문서화할 때:

```python
@pytest.mark.known_issue("왜 이 동작이 잘못되었는지")
def test_feature_scenario_expect_wrong_result() -> None:
    """현재(잘못된) 동작을 검증. 버그 수정 시 마커 제거 + 기대값 변경."""
    assert buggy_function() == "wrong_but_current_behavior"
```

`pyproject.toml`에 마커 등록:

```toml
[tool.pytest.ini_options]
markers = ["known_issue(reason): 알려진 버그"]
```

