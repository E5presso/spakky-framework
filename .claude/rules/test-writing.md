---
paths:
  - "**/tests/**/*.py"
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

## 실행 의무

- 테스트를 작성하거나 수정한 후 **반드시 실행하여 통과를 확인**한다
- "작성만 하고 넘어가기" 금지

## Flaky 테스트 금지

- `time.sleep`, `datetime.now()` 직접 의존 금지 — `freezegun` 또는 clock fixture 사용
- 테스트 실행 순서에 의존하는 공유 상태 금지
- 외부 네트워크 호출 금지 — mock/fake로 대체

## 커버리지

- **브랜치 커버리지 우선**: `--cov-branch` 활성화 상태에서 100% 목표
- 누락 브랜치는 테스트 추가로 해결 (pragma: no branch는 최후 수단)

## 시나리오 기반 테스트 품질

- **커버리지 패딩 금지**: 단순히 라인/브랜치를 실행만 하는 의미 없는 테스트 금지
- 모든 테스트는 **실제 유즈케이스 시나리오**를 반영해야 한다
- 각 테스트는 명확한 **입력 → 행위 → 기대 결과**를 검증한다
- 정상 경로(happy path)뿐 아니라 **경계값, 에러 경로, 엣지 케이스**를 시나리오로 작성한다
- 하나의 테스트에 여러 시나리오를 섞지 않는다 — 시나리오 당 하나의 테스트 함수
- `assert` 하나 없이 호출만 하는 테스트 금지 — 반드시 결과를 검증한다

## 테스트 패키지 구조

- **Unit**: `tests/unit/` 하위에 소스 패키지 구조를 미러링
- **Integration**: `tests/integration/` 하위에 시나리오/유스케이스 기준으로 구성

## Known Issue

```python
@pytest.mark.known_issue("이유")
def test_buggy_behavior_expect_wrong_result() -> None: ...
```
