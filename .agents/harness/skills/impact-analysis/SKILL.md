---
name: impact-analysis
description: 모노레포에서 특정 패키지/모듈 변경이 다른 패키지에 미치는 영향을 의존성 그래프 기반으로 분석합니다.
argument-hint: "<패키지명 또는 변경 설명>"
user-invocable: true
---

# Impact Analysis — 변경 영향 분석

특정 패키지나 모듈의 변경이 모노레포 전체에 미치는 영향을 의존성 그래프 기반으로 분석한다. 변경 전 리스크 평가 또는 변경 후 검증 범위 결정에 사용한다.

## 사용법

```
/impact-analysis spakky-domain
/impact-analysis "Entity 베이스 클래스의 __eq__ 변경"
/impact-analysis core/spakky-event/src/spakky/event/publisher.py
```

인자: 패키지명, 변경 설명, 또는 파일 경로

---

## Phase 1: 변경 대상 식별

### 1-1. 입력 분류

- **패키지명**: 해당 패키지 전체를 변경 대상으로 설정
- **파일 경로**: 해당 파일과 파일이 공개하는 심볼을 변경 대상으로 설정
- **변경 설명**: Explore 서브에이전트로 관련 코드를 탐색하여 변경 대상을 결정
- **인자 없음**: `git diff --name-only`로 현재 변경된 파일에서 자동 감지

### 1-2. 공개 인터페이스 추출

변경 대상의 공개 인터페이스를 추출한다:

- **`__all__`**: 명시적 export 목록
- **ABC/Protocol 클래스**: 하위 구현체에 영향
- **데코레이터 시그니처**: 사용처에 영향
- **이벤트 타입**: 발행/구독 양쪽에 영향

## Phase 2: 의존성 그래프 분석

### 2-1. 패키지 레벨 의존성

`monorepo.md`와 각 패키지의 `pyproject.toml`에서 패키지 간 의존 관계를 파악한다:

```bash
# 각 패키지의 의존성 확인
grep -A 20 "\[project\]" core/*/pyproject.toml plugins/*/pyproject.toml | grep "spakky"
```

의존성 방향 (ARCHITECTURE.md 기준):
```
spakky → spakky-domain → spakky-data → spakky-event → spakky-outbox
spakky → spakky-tracing → spakky-event
spakky → spakky-task
plugins → core (단방향)
```

### 2-2. 심볼 레벨 의존성

변경 대상의 공개 심볼(클래스, 함수, 상수)을 **다른 패키지에서 import하는 곳**을 탐색한다:

```bash
# 변경된 모듈의 심볼을 import하는 코드 탐색
grep -rn "from spakky.{모듈}" core/*/src/ plugins/*/src/ --include="*.py"
grep -rn "import spakky.{모듈}" core/*/src/ plugins/*/src/ --include="*.py"
```

### 2-3. 테스트 의존성

변경 대상을 사용하는 테스트 파일을 탐색한다:

```bash
grep -rn "from spakky.{모듈}\|import spakky.{모듈}" core/*/tests/ plugins/*/tests/ --include="*.py"
```

## Phase 3: 영향 범위 산정

### 3-1. 직접 영향

변경 대상을 **직접 import하거나 사용하는** 패키지/모듈:

- import 문에서 변경된 심볼을 참조
- ABC/Protocol을 구현하는 하위 클래스
- 데코레이터를 사용하는 코드

### 3-2. 간접 영향 (전이적)

직접 영향을 받는 모듈이 **다시 공개하는 인터페이스**를 통해 간접적으로 영향을 받는 패키지:

- re-export 체인
- 의존성 그래프에서 2홉 이상 떨어진 패키지

### 3-3. 리스크 등급

| 등급 | 기준 | 필요 조치 |
|------|------|----------|
| 🔴 **Breaking** | 공개 인터페이스(시그니처, 반환 타입) 변경 | 모든 하위 구현체 + 사용처 수정 필수 |
| 🟡 **Behavioral** | 동작 변경 (예외 타입, 부수 효과) | 관련 테스트 재실행 필수 |
| 🟢 **Internal** | 내부 구현만 변경, 공개 인터페이스 불변 | 해당 패키지 테스트만 재실행 |

## Phase 4: 결과 보고

```
## 영향 분석 결과

### 변경 대상
{패키지/모듈/심볼 요약}

### 영향 그래프

{Mermaid 다이어그램 — 변경 대상에서 영향받는 패키지로 화살표}

### 직접 영향

| 패키지 | 영향 모듈 | 리스크 | 영향 내용 |
|--------|----------|--------|----------|
| {패키지} | {모듈} | 🔴/🟡/🟢 | {구체적 영향} |

### 간접 영향

| 패키지 | 경유 | 리스크 | 영향 내용 |
|--------|------|--------|----------|
| {패키지} | {경유 패키지} | 🟡/🟢 | {구체적 영향} |

### 검증 필요 패키지

변경 후 `/check`를 실행해야 하는 패키지 목록 (우선순위순):

1. {패키지A} — 🔴 Breaking: {사유}
2. {패키지B} — 🟡 Behavioral: {사유}
3. {패키지C} — 🟢 Internal: {사유}

### 요약

- 직접 영향: {N}개 패키지
- 간접 영향: {M}개 패키지
- 최대 리스크: {🔴/🟡/🟢}
```

---

## 규칙

- 의존성 분석은 **코드 기반**으로 수행한다 — `pyproject.toml` + 실제 import 문 교차 검증.
- 코드 탐색은 **Explore 서브에이전트**로 실행하여 메인 컨텍스트를 보존한다.
- Mermaid 다이어그램은 `mermaid.md` 규칙을 따른다.
- 영향이 없는 패키지를 "혹시 모르니" 포함하지 않는다 — 증거 기반으로만 목록에 추가.
- 리스크 등급은 공개 인터페이스 변경 여부로 판단한다 — 내부 구현 변경은 항상 🟢.

$ARGUMENTS
