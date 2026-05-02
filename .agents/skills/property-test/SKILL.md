---
name: property-test
description: 대상 모듈의 속성 기반 테스트(Hypothesis)를 자동 생성합니다. DI 컨테이너, AOP, 이벤트 등 불변식 검증에 특화.
argument-hint: "<패키지명 또는 모듈 경로>"
user-invocable: true
---

# Property Test — 속성 기반 테스트 자동 생성

대상 모듈을 분석하여 Hypothesis 기반 속성 테스트를 자동 생성한다. 단위 테스트가 놓치기 쉬운 엣지 케이스와 불변식 위반을 탐지한다.

## 사용법

```
/property-test spakky
/property-test core/spakky-domain/src/spakky/domain/models
```

인자: 패키지명 또는 모듈 경로

---

## Phase 1: 대상 분석

### 1-1. 대상 결정

- **패키지명**이면 해당 패키지의 `src/` 디렉토리를 대상으로 한다.
- **모듈 경로**이면 해당 경로를 대상으로 한다.

### 1-2. 패턴 탐지

**Explore 서브에이전트**로 대상 코드를 분석하여, 아래 패턴 중 해당하는 것을 식별한다:

| 우선순위 | 패턴 | 속성 테스트 적합성 | 예시 |
|---------|------|-------------------|------|
| **1** | 직렬화/역직렬화 쌍 | `decode(encode(x)) == x` | `to_dict` / `from_dict` |
| **2** | 불변식을 가진 모델 | 생성 후 불변식 항상 성립 | Entity ID 불변, ValueObject 동등성 |
| **3** | 멱등 연산 | `f(f(x)) == f(x)` | 캐시, 정규화, DI resolve |
| **4** | 교환/결합 법칙 | `f(a, b) == f(b, a)` | 이벤트 핸들러 등록 순서 무관 |
| **5** | 입력 검증 | 유효 입력 → 성공, 무효 입력 → 특정 예외 | 데코레이터 파라미터 검증 |
| **6** | 상태 머신 | 상태 전이 시퀀스가 항상 유효 | 컨테이너 라이프사이클 |

### 1-3. 기존 테스트 확인

- 이미 Hypothesis 테스트가 있는지 확인한다.
- 기존 단위 테스트의 커버리지를 확인하여 부족한 영역을 파악한다.

**산출물**: 탐지된 패턴 목록 (패턴 유형, 대상 클래스/함수, 검증할 속성)

## Phase 2: 전략 수립

### 2-1. 커스텀 전략 설계

탐지된 패턴별로 Hypothesis 전략(`@st.composite`)을 설계한다:

- **도메인 모델**: 모델의 제약 조건을 반영한 커스텀 전략
  ```python
  @st.composite
  def entity_ids(draw: st.DrawFn) -> EntityId:
      # EntityId의 제약 조건을 반영
      ...
  ```
- **DI 컨테이너**: 컴포넌트 그래프를 생성하는 전략
- **이벤트**: 이벤트 객체와 핸들러 조합을 생성하는 전략

### 2-2. 사용자 확인

탐지 결과와 생성 계획을 사용자에게 제시한다:

```
## 속성 테스트 생성 계획

### 탐지된 패턴

| # | 패턴 | 대상 | 검증할 속성 |
|---|------|------|-----------|
| 1 | {패턴} | {클래스/함수} | {속성} |

### 생성할 테스트 파일

- `tests/property/test_{모듈명}_properties.py`
```

`AskUserQuestion`으로 승인을 받는다:

```yaml
question: "위 속성 테스트 생성 계획을 승인하시겠습니까?"
header: "속성 테스트 계획"
options:
  - label: "승인"
    description: "계획대로 테스트를 생성합니다"
  - label: "수정"
    description: "특정 패턴을 추가/제거합니다 (notes에 기재)"
  - label: "취소"
    description: "테스트 생성을 취소합니다"
```

## Phase 3: 테스트 생성

### 3-1. 테스트 코드 작성

각 패턴에 대해 속성 테스트를 작성한다:

```python
from hypothesis import given, settings, assume
import hypothesis.strategies as st


@given(...)
@settings(max_examples=100)
def test_{속성_이름}(...) -> None:
    """속성: {검증할 속성을 자연어로 기술}"""
    ...
```

### 작성 원칙

- **함수 기반 테스트**: `class TestXxx` 사용 금지 (프로젝트 컨벤션)
- **테스트 파일 위치**: 패키지의 `tests/property/` 디렉토리
- **conftest.py**: 커스텀 전략은 `tests/property/conftest.py`에 정의
- **독립성**: 각 테스트는 독립적으로 실행 가능해야 한다
- **`@settings`**: `max_examples=100` 기본값 (CI 시간 고려)

### 3-2. Hypothesis 의존성 확인

패키지의 `pyproject.toml`에 `hypothesis`가 테스트 의존성에 있는지 확인한다:

```bash
cd <package-dir> && grep -q "hypothesis" pyproject.toml
```

없으면 추가한다:

```bash
cd <package-dir> && uv add --dev hypothesis
```

## Phase 4: 검증

### 4-1. 테스트 실행

```bash
cd <package-dir> && uv run pytest tests/property/ -v
```

### 4-2. 실패 분석

- **속성 위반 발견**: 이는 **버그 발견**이다. 반례(counterexample)를 기록하고 사용자에게 보고한다.
- **전략 오류**: 커스텀 전략이 유효하지 않은 입력을 생성하면 전략을 수정한다.
- **타임아웃**: `max_examples`를 줄이거나 전략을 단순화한다.

### 4-3. 결과 보고

```
## 속성 테스트 결과

생성: {N}개 테스트 ({M}개 파일)
통과: {P}개
실패: {F}개

### 발견된 속성 위반 (있으면)

| 테스트 | 반례 | 위반된 속성 |
|--------|------|-----------|
| {테스트명} | {반례} | {속성 설명} |
```

---

## 규칙

- Hypothesis가 발견한 속성 위반은 **버그**로 취급한다 — 테스트를 제거하지 않고 코드를 수정한다.
- 기존 단위 테스트와 중복되는 단순 예시 테스트는 작성하지 않는다 — 속성 테스트의 가치는 **자동 엣지 케이스 탐색**에 있다.
- 코드 탐색은 **Explore 서브에이전트**로 실행한다.
- `uv run` 접두사 필수.
- **루트에서 직접 실행 금지** — 반드시 패키지 디렉토리 내에서 실행.

$ARGUMENTS
