---
name: adr
description: 현재 코드베이스의 ADR 상태를 감사하고, 미문서화된 아키텍처 결정을 감지하여 ADR 작성을 제안합니다.
argument-hint: "[패키지명 또는 주제]"
user-invocable: true
---

# ADR Audit — 아키텍처 결정 감사

코드베이스에서 **암묵적으로 내려졌지만 문서화되지 않은 아키텍처 결정**을 감지하고, ADR 작성을 제안한다.

> **관련 스킬**: ADR 작성 자체는 → `/decide-architecture`

## 사용법

```
/adr
/adr spakky-event
/adr "이벤트 전파 전략"
```

- 인자 없음: 전체 코드베이스를 감사
- 패키지명: 해당 패키지만 감사
- 주제: 특정 주제에 대해 ADR 필요성을 검토

---

## Phase 1: 기존 ADR 수집

1. `docs/adr/README.md`를 읽어 기존 ADR 목록을 파악한다.
2. 각 ADR의 상태(Accepted, Superseded, Deprecated)를 기록한다.
3. ADR이 다루는 주제를 키워드로 정리한다.

## Phase 2: 미문서화 결정 탐지

**Explore 서브에이전트**로 아래 시그널을 탐색한다:

### 탐지 시그널

| 시그널 | 탐색 방법 | ADR 필요 가능성 |
|--------|----------|----------------|
| **패턴 선택** | 특정 디자인 패턴이 반복 사용되는데 ADR이 없음 | 높음 |
| **대안 흔적** | 주석에 "대안", "고려", "선택", "이유" 키워드 | 높음 |
| **의존성 결정** | 외부 라이브러리 선택이 ADR에 없음 | 중간 |
| **인터페이스 설계** | ABC/Protocol 정의가 ADR 없이 존재 | 중간 |
| **컨벤션** | 네이밍/구조 패턴이 CONTRIBUTING.md에만 있고 ADR에 없음 | 낮음 |
| **최근 대규모 변경** | `git log`에서 `refactor:` 커밋이 ADR 없이 존재 | 중간 |

### 탐색 명령 예시

```bash
# 대안/선택 흔적이 있는 주석 탐색
grep -rn "대안\|alternative\|instead of\|chose\|선택\|이유" core/*/src/ plugins/*/src/ --include="*.py"

# ABC/Protocol 정의 탐색
grep -rn "class.*ABC\|class.*Protocol" core/*/src/ plugins/*/src/ --include="*.py"

# 최근 대규모 refactor 커밋
git log --oneline --all --grep="refactor" -20
```

## Phase 3: 갭 분석

### 3-1. 교차 대조

탐지된 결정들을 기존 ADR 목록과 교차 대조하여 **갭**을 식별한다:

- **문서화됨**: 기존 ADR에서 다루고 있음 → 스킵
- **부분 문서화**: ADR이 있지만 최신 코드와 불일치 → 업데이트 필요
- **미문서화**: ADR이 전혀 없음 → 신규 작성 필요

### 3-2. 우선순위 산정

미문서화 결정을 아래 기준으로 우선순위를 매긴다:

| 기준 | 가중치 |
|------|--------|
| 여러 패키지에 영향을 미치는 결정 | 높음 |
| 외부 기여자가 혼란을 겪을 수 있는 결정 | 높음 |
| 대안이 명확히 존재하는 결정 | 중간 |
| 단일 패키지 내부 결정 | 낮음 |

## Phase 4: 결과 보고

```
## ADR 감사 결과

### 기존 ADR 현황
- 총 {N}개 ADR (Accepted: {A}, Superseded: {S})

### 미문서화 아키텍처 결정

| 우선순위 | 주제 | 시그널 | 관련 패키지 | 권장 액션 |
|---------|------|--------|-----------|----------|
| 🔴 높음 | {주제} | {시그널} | {패키지} | ADR 신규 작성 |
| 🟡 중간 | {주제} | {시그널} | {패키지} | ADR 업데이트 |

### 업데이트 필요 ADR

| ADR | 불일치 내용 |
|-----|-----------|
| {ADR-NNNN} | {현재 코드와 다른 점} |
```

### 다음 액션

`AskUserQuestion`으로 다음 행동을 묻는다:

```yaml
question: "어떤 ADR을 작성/업데이트할까요?"
header: "ADR 감사 완료"
options:
  - label: "ADR 작성"
    description: "선택한 주제로 /decide-architecture를 실행합니다 (notes에 주제 기재)"
  - label: "일괄 생성"
    description: "높은 우선순위 항목을 모두 ADR로 작성합니다"
  - label: "종료"
    description: "감사 결과만 확인하고 종료합니다"
```

- "ADR 작성" 선택 시 `/decide-architecture {주제}`를 실행한다.
- "일괄 생성" 선택 시 높은 우선순위 항목을 순차적으로 `/decide-architecture`로 처리한다.

---

## 규칙

- ADR은 **검증된 사실**만 기록한다 — "아마도", "~일 수 있음" 형태의 추측을 ADR에 넣지 않는다.
- 코드 탐색은 **Explore 서브에이전트**로 실행한다.
- 기존 ADR과 중복되는 주제를 새로 생성하지 않는다 — 업데이트를 권장한다.
- ADR 작성 자체는 이 스킬이 아닌 `/decide-architecture`에 위임한다.

$ARGUMENTS
