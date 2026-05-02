---
paths:
  - "**/*.py"
---

# 리뷰 휴리스틱 / YAGNI 역설

리뷰 에이전트가 **구체적 탐지 시그널**을 기반으로 의문점을 생성하는 원천. 시그널이 매치될 때만 의문을 꺼낸다 — 개방형 "왜?" 질문 금지.

## 원칙 1 — 이질성 (Heterogeneity)

레포 다른 곳에 없는 패턴은 의문. `Grep`으로 선례 확인 후 같은 패턴 따른다 — **단, 무엇에 대한 선례인지 구분**한다.

### 1-A. 기능적·아키텍처적 결정 → 코드베이스가 SSOT

도메인 모델 형태, 레이어 의존 방향, 외부 시스템 통합 패턴, ABC (Abstract Base Class) vs class 기반, async vs sync 경계, Pydantic vs dataclass 같이 **시스템이 어떻게 동작하는가**에 대한 결정은 레포 선례가 정당성을 가진다 — 새 코드는 기존 선례를 따라야 정합성이 유지된다.

시그널: 기존 class 기반 도메인에 closure 데코레이터, 기존 Pydantic 모델에 dataclass, 기존 `async` 호출 경로에 동기 함수, 외부 시스템 통합에 새 라이브러리 도입.

### 1-B. 코딩 스타일 → 코드베이스는 SSOT 아님 (레거시는 개선 대상)

타입 표기(`List[T]` vs `list[T]`), generic syntax(`Generic[T]` vs PEP 695 `[T]`), `from __future__ import annotations` 사용, `Optional[T]` vs `T | None`, 식별자 명명 일관성, 주석 정책 같은 **어떻게 표기하는가**에 대한 결정은 레포 선례가 정당성을 주지 않는다.

> 모든 코드베이스는 저마다의 레거시를 갖고 있으며, 이를 꾸준히 개선하는 것은 개발자의 책무다. 이미 그런 스타일의 코드가 있었다고 해서 새 코드도 그렇게 써도 된다는 의미는 아니다.

새 코드는 charter §2 / `python-code.md` "최신 문법" / `type-discipline.md` 같은 **대원칙 SSOT**를 따른다. 같은 파일·도메인 안에 신구 스타일이 혼재하면 새 코드는 신스타일로 통일하고, 레거시 정리가 필요하면 후속 티켓 분기(`/plan-issues`)로 처리.

시그널: 새 코드에 `List[T]`/`Dict[K,V]`/`Optional[T]` 답습, `from __future__ import annotations` 답습, `TypeVar` 명시 선언 (PEP 695로 풀릴 케이스), 구식 isinstance 체인 (match/case로 풀릴 케이스).

## 원칙 2 — 동적성 (Dynamism)

정적 분석이 닿지 않는 코드는 의문. 타입 체커가 추론 포기하는 지점은 리팩터링 비용이 큼.

시그널: `pydantic.create_model` 런타임 스키마 합성, `getattr`/`hasattr`/`setattr`, 메타클래스 트릭(`__init_subclass__`), `exec`/`eval`.

대안: 정적 `BaseModel`, Generic 타입 파라미터, 수기 JSON Schema.

## 원칙 3 — 은폐 (Opacity)

내부 상태가 숨겨지면 의문. 테스트·디버깅의 주입·관찰 지점을 가리는 구조.

시그널: closure 스코프 상태 캡처, context manager 없는 수동 clean-up, 전역 변수 상태, 은닉 singleton, closure 데코레이터 미들웨어(→ class-based 미들웨어 선호).

## 원칙 4 — 강제 부재 (Unenforced Contract)

계약이 런타임 검증에만 의존하면 의문. 타입·인터페이스로 계약을 강제할 수 있는 구간은 강제한다.

시그널: 타입 힌트 없는 dict 반환, post-hoc `model_validate`만으로 외부 입력 보장, 선택 필드가 도메인 불변식을 깨는 케이스.

## 원칙 5 — YAGNI 역설 (Premature Generalization / Domain Incompleteness)

"You Aren't Gonna Need It"이 기본이지만, **도메인 완전성**·**구조적 일관성**을 해치는 YAGNI (You Aren't Gonna Need It)는 안티패턴.

**과소 일반화 의문:**
- 복수 호출자가 도메인상 자명한데 일반화되지 않은 구조 (`BaseContextExtractor`가 한 종류에만 바인딩).
- 같은 필드 묶음이 여러 시그니처에 반복(통합 DTO (Data Transfer Object) 부재).
- 세마포어·concurrency 제한·backoff 같은 인프라 유틸이 특정 usecase에 귀속 — 처음부터 공통 위치에 일반화.

**과잉 추상화 의문:** 하나의 서브클래스만 가진 `BaseXxx`, 구현체 1개인 인터페이스, 구체 타입 1개에만 쓰는 제네릭 파라미터.

**도메인 완전성 > YAGNI (You Aren't Gonna Need It):**
- 기본 상태 필드(예: AggregateRoot 기본 상태, lineage summary)는 "현재 호출자가 안 쓴다"는 이유로 응답에서 빼지 않음.
- 스펙 자체가 누락된 케이스 발견 시 지금 수정 제안(→ `behavioral-guidelines.md` "스펙 검증").

**판단 기준:** 일반화는 (1) 기존 호출자를 깨지 않고 (2) 복수 미래 호출자가 도메인상 자명할 때만. 불확실하면 하지 않음.

**helper 추출과 DTO (Data Transfer Object) 통합은 다른 규율**: helper 추출은 로직 재사용(단일 사용 금지), DTO 통합은 데이터 구조 응집(중복 반복 시 통합).

## 원칙 6 — 중복 구조 (Redundant Structure)

같은 데이터 묶음이 여러 시그니처에 반복되면 의문. 통합 DTO (Data Transfer Object) 부재 신호.

시그널: 두 함수의 인자 3개가 동일, Request DTO (Data Transfer Object)와 Command DTO 필드 대부분 중첩, 여러 엔드포인트가 같은 pagination 파라미터 세트를 개별 정의.
