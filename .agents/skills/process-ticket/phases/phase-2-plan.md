# Phase 2: 구현 계획 수립

> **Phase 진입 ping** (sub-agent 한정): plan agent spawn 직전 1회 SendMessage(to: "team-lead", message: `phase: Phase 2 plan | issue: <N> | plan agent dispatched`). SKILL.md "Phase 전환 progress ping" SSOT.

## 2-0. 비즈니스 의도 재확인 (positive bias)

`charter.md` §2 "3-축 정렬" 수행 후 2-3줄 요약을 사용자에게 **비차단 1-way 공유**한다 — 회신 대기 없이 즉시 2-1로 진입.

**근거**: charter §5에 따라 구현 단계는 자율 진행이 기본. 의도 요약은 사용자가 PR 폼팩터에서 결정을 회수할 수 있도록 하는 투명성 장치이지, 인간 게이트가 아니다. 자동화 워크플로의 가치(인간 개입 최소화)를 보호하기 위해 회신 대기를 두지 않는다.

**차단 조건 (high-level policy 충돌만)**: 아래 중 하나라도 관찰되면 즉시 차단하고 사용자 판정을 질의한다 (charter §5 적용):

- charter §2 3-축 정렬에서 **명백한 충돌** — 이슈 어휘가 `domain.md`·`monorepo.md`·도메인 사전(AGENTS.md "프로젝트 특수 컨벤션")과 어긋남, 또는 이슈가 가정하는 산출물이 코드베이스에 다른 형태로 이미 존재
- 이슈 본문이 가정한 정책·규칙이 charter / behavioral-guidelines / domain rules와 정면 충돌
- 분해 단위 재정의 필요 신호 (이슈 스코프가 실제 작업과 어긋남 → `/plan-issues`로 후속 분기 필요)

**자명 생략 조건**: 단일 파일 단일 함수 변경, 오타·포맷·주석 수정, 기존 테스트 케이스 1건 추가 등 도메인 판단이 개입하지 않는 이슈는 요약 공유 자체를 생략. **단** GitHub 이슈의 milestone·sub-issues·blockedBy·related 필드를 Phase 1에서 실제 조회한 뒤에만 자명 판정 — 필드가 비어있고 본문도 단순해야 허용.

## 2-1. 코드 분석 + 판단 불확실 지점 식별

이슈 명세와 코드베이스를 교차대조하면서, **구현 시 임의 판단이 필요한 갈림길**을 함께 식별한다. 식별된 갈림길은 charter §5에 따라 **자율 결정과 사용자 질의 트리거를 구분**한다.

1. 관련 도메인 모델, 포트, 어댑터, 유스케이스, Aspect, Plugin을 탐색한다.
2. 코드 SSOT (`core/spakky*/src/`, `plugins/spakky-*/src/`) + 도메인 사전(AGENTS.md / ARCHITECTURE.md) + 관련 ADR(`docs/adr/`)만 참조한다. stale 가능성이 있는 외부 디자인 문서는 참조 금지.
3. 코드·도메인 사전·스펙 본문에서 **도출 가능한 결정은 자율 진행**한다 (charter §5). 자율 진행한 비자명한 결정은 **PR 본문/커밋 메시지에 결정 근거 1줄**을 남긴다 — 사용자는 PR 폼팩터에서 회수 가능.
4. **사용자 질의 트리거 (이것만)** — 아래에 해당하는 경우만 사용자 질의. **sub-agent로 실행 중이면 SKILL.md "사용자 질의 위임" 절의 `ask-delegate`로 메인에 위임**, 사용자 직접 호출이면 `AskUserQuestion` 직접:
   - **스펙 본문 ↔ 코드베이스 직접 충돌** (예: 스펙이 가정한 신규 Port가 다른 이름으로 이미 존재)
   - **도메인 사전 미등록 신규 어휘 도입 필요** — 코드에 박기 전 사전 등록 합의
   - **이슈 분해 단위 재정의 필요** — "대상이 많다"는 이유로 분리하는 게 아니라, 이슈가 가정한 관심사 경계가 실제 코드와 어긋날 때만. 같은 관심사의 반복 적용은 한 PR로 수행하는 게 default (→ `plan-issues` 분해 원칙).
   - **정책·규칙 위반 가능성** (charter / behavioral-guidelines / domain rules와의 충돌)
   - **외부 시스템 mutation·destructive action**
   - **하네스 교정** — 변경 경로가 `.agents/skills/`·`.agents/rules/`·`AGENTS.md` (또는 동등 하네스 자산)을 포함하면 plan summary를 `ask-delegate`로 메인에 질의하고 회신 수신 후에만 Phase 5 진입한다. 하네스는 후속 모든 세션의 행동을 결정하는 SSOT이므로 sub-agent의 "low risk·single-file edit" 자가 판정으로 우회할 수 없다. 사용자 직접 호출이면 `AskUserQuestion` 직접.
5. **자율 진행 명시 영역 (사용자 질의 금지)**:
   - 변수명, 메서드 시그니처 디테일, import 경로, 타입 좁히기 방식
   - 헬퍼 분리 여부, 테스트 파일 위치, fixture 구성
   - DI (Dependency Injection) 주입 형태가 코드·도메인 사전으로 결정 가능한 경우 — 경계가 불분명한 경우에도 우선 코드·사전·스펙 본문을 재탐색하여 해소한다. 3개 모두를 탐색해도 결정 불가능할 때만 4번 트리거(스펙↔코드 충돌)로 전환.
   - "동작 명세가 빠진 것처럼 보이는" 수용 기준 — 이슈 본문의 acceptance scenario · 도메인 계약 · edge case 로 도출 가능한 경우 자율 결정. 본문에 명시된 단어로 답이 나오지 않을 때만 4번 트리거.

## 2-2. 계획 수립

1. **Plan agent (opus)**를 사용하여 구현 계획을 수립한다.
2. 계획 수립 시 준수 사항:
   - 프로젝트 AGENTS.md의 모든 규칙
   - `.agents/rules/charter.md` (헌장)
   - `.agents/rules/behavioral-guidelines.md`의 행동 원칙
   - `.agents/rules/python-code.md`, `.agents/rules/domain.md`, `.agents/rules/aspect.md`, `.agents/rules/plugin.md`, `.agents/rules/monorepo.md`
   - 레이어 의존 방향 (외부 → 내부만 허용)
3. 2-1에서 **코드로 해소하지 못한 판단 불확실 지점**이 있으면, 계획에 "판단 사항" 섹션을 추가하여 사용자 승인 시 함께 확인받는다.

## 2-3. 사용자 승인

> `--require-approval` 플래그가 지정되지 않은 경우(기본값) 이 단계를 건너뛰고 Phase 3으로 즉시 진행한다.
> `--overnight` 모드에서는 `--require-approval`이 같이 지정되어도 이 단계를 항상 건너뛴다.

구현 계획을 사용자에게 제시하고 승인을 받는다.
- 승인 없이 다음 단계로 진행하지 않는다.
- **sub-agent로 실행 중이면 SKILL.md "사용자 질의 위임" 절의 `ask-delegate`로 메인에 위임** (`phase: Phase 2-3`, `trigger: plan-approval`). 사용자 직접 호출이면 아래 `AskUserQuestion` 직접:
  ```yaml
  question: "위 구현 계획을 승인하시겠습니까?"
  header: "계획 승인"
  options:
    - label: "승인"
      description: "계획대로 구현을 시작합니다"
    - label: "수정 요청"
      description: "계획의 특정 부분을 변경합니다 (notes에 수정 내용 기재)"
    - label: "재수립"
      description: "계획을 처음부터 다시 수립합니다"
  ```
- "수정 요청" 선택 시 사용자의 notes를 반영하여 계획을 갱신한 뒤 다시 승인을 요청한다.
- "재수립" 선택 시 Phase 2를 처음부터 재실행한다.
