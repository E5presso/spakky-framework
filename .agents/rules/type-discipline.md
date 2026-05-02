---
paths:
  - "**/*.py"
---

# 타입 규율

타입은 **비즈니스 의미를 부호화하는 수단**이다. 단순한 타입 안전성을 넘어 도메인 의도를 타입 시스템에 인코딩한다.

## 1. 범용 타입 금지 (Public Signature)

함수·메서드의 public 시그니처에 다음을 직접 사용하지 않는다:

- `str`, `int`, `dict`, `list`, `tuple` (의미 없는 raw 타입)
- `dict[str, Any]`, `list[dict]` (구조 미정 컨테이너)

대신 **의미 있는 타입**으로 부호화한다:

```python
# 금지
def assign(user_id: str, role: str) -> None: ...

# 허용 (Type Alias)
type UserId = str
type Role = Literal["admin", "member", "guest"]
def assign(user_id: UserId, role: Role) -> None: ...

# 허용 (VO)
class UserId(ValueObject):
    value: UUID
def assign(user_id: UserId, role: Role) -> None: ...
```

## 2. Pydantic BaseModel 우선

DTO·요청/응답·외부 직렬화가 필요한 데이터 구조는 `pydantic.BaseModel`을 우선 사용한다. 이유: 검증·직렬화·스키마 생성·`json_format` 변환을 한 번에 얻는다.

`@dataclass`는 다음 경우만 허용:
- 외부 라이브러리(`langchain`, `kafka-python` 등)가 직접 instance 검사를 요구할 때
- 도메인 VO가 hash/equality semantics만 필요하고 직렬화 불필요할 때

## 3. None 허용의 도메인 근거

`Optional[T]` (= `T | None`)을 쓰려면 도메인 의미를 명확히 한다:

| None 의미 | 예시 | 처리 |
|----------|------|------|
| **미계산** | `total: int \| None` (집계 미실행) | 도메인 메서드로 채움 |
| **해당 없음** | `parent_id: UUID \| None` (루트 노드) | 분기 처리 |
| **미지정** | `nickname: str \| None` (선택 입력) | 기본값 또는 분기 |

위 셋 중 어느 의미인지 모호한 `Optional`은 타입을 무너뜨린다. 1줄 주석 또는 docstring으로 의미 명시.

## 4. Enum / Literal로 분기 도메인 부호화

분기 가능한 상태·종류는 `enum.Enum` 또는 `Literal`로:

```python
# 금지
def transition(status: str) -> None:
    if status == "pending": ...
    elif status == "approved": ...

# 허용
class OrderStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
def transition(status: OrderStatus) -> None:
    match status:
        case OrderStatus.PENDING: ...
        case OrderStatus.APPROVED: ...
```

`match` 문과 결합 시 `Literal` 타입 누락이 컴파일 단계에서 검출된다.

## 5. `Any` 금지 (정당화 없이)

`Any`·`object`·`cast()`를 사유 없이 사용하지 않는다. 사용하려면 1줄 주석으로 정당화:

```python
# 외부 라이브러리 X가 untyped — 1.2.3에서 stub 제공 예정 (issue #YYY)
result: Any = legacy_lib.fetch()
```

## 6. `@override` 누락 금지

부모 메서드를 재정의하면 `typing.override` 데코레이터 필수. 누락 시 부모 시그니처 변경에 무방비.

```python
from typing import override

class Sub(Base):
    @override
    def execute(self) -> None: ...
```

## 7. TypedDict보다 BaseModel

`dict` 형태의 데이터 구조가 필요하면 `TypedDict`보다 `BaseModel`을 우선. 이유:
- 런타임 검증
- `model_validate` / `model_dump` 일관 인터페이스
- IDE 자동완성·refactoring 지원
