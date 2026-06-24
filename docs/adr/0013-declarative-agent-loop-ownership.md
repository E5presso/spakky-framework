# ADR-0013: 선언형 Agent — 프레임워크 루프 소유·프로토콜 중립 코어·AG-UI/A2A/MCP 어댑터

- **상태**: Accepted
- **날짜**: 2026-06-24
- **선행**: [ADR-0009 Agentic Hexagonal Architecture](0009-agentic-hexagonal-architecture.md)
- **대체**: 해당 없음

## 맥락 (Context)

[ADR-0009](0009-agentic-hexagonal-architecture.md)는 `@Agent`를 `@UseCase`와 동격인 `@Pod` stereotype으로 모델링하고, `execute()`가 `AgentYield` stream을 반환하며, model/tool/state/signal/evidence를 building block으로 제공한다는 큰 그림을 확정했다. 그 마일스톤에서 `@Agent.execute()` 본문은 model stream을 직접 소비하고, tool call을 직접 invoke하며, approval/final 분기를 직접 작성하는 **명령형 루프**였다 (ADR-0009 "마일스톤 성공 그림"의 `CodeAssistant.execute()` 예시 참조).

마일스톤 #19 (DX 개선)에서 선언형 Agent로 전환하는 방향을 사용자와 길게 논의했다. 핵심 질문은 두 가지였다.

1. **누가 agent 실행 루프를 소유하는가** — 개발자가 `while True: async for event in model.stream(...)` 루프를 매번 직접 쓰는가, 아니면 프레임워크가 루프를 소유하고 개발자는 설정만 선언하는가.
2. **AG-UI·A2A·MCP라는 세 외부 프로토콜을 코어가 어떻게 수용하는가** — 코어가 특정 프로토콜을 직접 채택하는가, 중간 변환 plugin을 두는가, 아니면 코어를 프로토콜 중립으로 두고 어댑터로 분리하는가.

ADR-0009는 이 두 결정을 명시적으로 닫지 않았다 (`spakky-agent-mcp`/`spakky-agent-a2a`를 "첫 마일스톤 범위 밖"으로만 표기). 본 ADR은 그 공백을 닫고, 후속 구현 그룹(C·D·E·F)이 따르는 단일 근거를 박제한다. 이 ADR은 ADR-0009를 대체하지 않고 그 위에 선언형 실행 모델과 프로토콜 경계를 얹는다.

비교 기준점은 pydantic-ai다. pydantic-ai는 `Agent` 객체가 실행 루프를 소유하고(`agent.run()`/`run_stream()`), tool은 `@agent.tool` 데코레이터로 선언하며, model은 생성자/실행 인자로 주입하고, 외부 프로토콜은 `pydantic_ai.ui.ag_ui`(AG-UI 어댑터)와 `fasta2a`(A2A 어댑터)로 코어 밖에서 normalize한다. 코어 자체는 어떤 UI/transport 프로토콜에도 의존하지 않는다. 이 DX(개발자가 비즈니스 로직만 선언하고 루프·프로토콜은 프레임워크가 제공)가 본 ADR이 정렬하려는 목표다.

## 결정 동인 (Decision Drivers)

- 개발자가 작성하는 코드의 비율을 비즈니스 의도(어떤 tool·어떤 model·어떤 정책)로 최대화하고, 반복적인 model-loop 배관 코드를 0에 수렴시킨다.
- ADR-0009가 확정한 `@Agent`/`@UseCase` 동격성, 생성자 DI 의존성 주입, hexagonal 레이어 경계를 깨지 않는다.
- 외부 프로토콜이 하나가 아니다 — AG-UI(클라이언트↔에이전트 UI streaming), A2A(에이전트↔에이전트 위임), MCP(에이전트↔외부 tool/server)는 서로 다른 계층의 서로 다른 계약이다. 코어가 어느 하나를 직접 채택하면 나머지 둘이 종속·왜곡된다.
- 코어는 외부 프로토콜 라이브러리에 의존하지 않는다 (ADR-0009 검증 기준 "`core/spakky-agent`는 외부 protocol server에 직접 의존하지 않는다"의 연장).
- HITL(Human-In-The-Loop), 멀티턴 세션, context compaction 같은 cross-cutting 실행 관심사는 개발자 루프 본문이 아니라 프레임워크 실행 루프가 일관되게 처리해야 재현 가능하고 복구 가능하다.
- v6.10.0 minor 릴리스이며 현재 외부 고객(production 소비자)이 없으므로, ADR-0009의 명령형 `execute()` 예시 대비 하드 브레이크를 허용한다.

## 고려한 대안 (Considered Options)

프로토콜 수용 축에서 세 가지 대안을 검토했다.

### 대안 α: 코어가 AG-UI를 직접 채택

`core/spakky-agent`가 `ag_ui` 라이브러리를 직접 import하고, `AgentYield` 대신 AG-UI `BaseEvent` taxonomy를 코어 1차 이벤트 모델로 삼는다. 어댑터 레이어 없이 `@Agent.execute()` stream이 곧 AG-UI 이벤트 stream이다.

기각 이유:

- AG-UI는 **클라이언트↔에이전트 UI streaming** 프로토콜이다. A2A(에이전트 간 위임)와 MCP(외부 tool 호출)는 AG-UI 이벤트 모델로 표현되지 않는 별도 계약이다. 코어를 AG-UI에 고정하면 A2A delegation과 MCP tool 호출이 AG-UI 이벤트로 억지 매핑되어 왜곡된다.
- 코어가 외부 프로토콜 라이브러리(`ag_ui`)에 의존하게 되어 ADR-0009의 "코어 비의존" 검증 기준을 위반한다.
- AG-UI 스펙 버전 변경이 코어 public contract를 직접 깬다.

### 대안 β: 코어와 프로토콜 사이에 중간 mapper plugin

코어는 자체 이벤트 모델을 유지하되, `spakky-agent-protocol-mapper` 같은 단일 중간 plugin이 코어 이벤트를 모든 외부 프로토콜로 양방향 변환하는 단일 책임을 진다. 각 프로토콜 어댑터는 이 mapper를 경유한다.

기각 이유:

- 세 프로토콜은 변환 모양이 근본적으로 다르다 (AG-UI=outbound event stream, A2A=Task 상태 머신 + AgentCard discovery, MCP=tool descriptor 정규화). 단일 mapper는 세 변환의 공약수가 거의 없는 god-object가 되거나, 내부적으로 다시 세 갈래로 분기하여 어댑터 분리와 동형이 된다.
- mapper가 코어와 어댑터 사이의 불필요한 pass-through 레이어가 된다 (`behavioral-guidelines.md` §2 "필요 없는 wrapper/resolve 레이어 제거" 위반). 어댑터가 코어 이벤트를 직접 소비하면 되는데 중간 계약을 하나 더 만든다.
- pydantic-ai 선례와 어긋난다 — pydantic-ai는 중간 mapper 없이 `ui.ag_ui` 어댑터와 `fasta2a` 어댑터가 코어 message/event를 직접 소비한다.

### 대안 γ: 프로토콜 중립 코어 + 프로토콜별 어댑터 분리 (채택)

코어는 어떤 외부 프로토콜에도 의존하지 않는 **중립 이벤트 taxonomy**와 실행 루프만 소유한다. 각 프로토콜은 독립 어댑터가 코어 이벤트를 자신의 프로토콜로 normalize한다.

- AG-UI 어댑터 → `ag_ui` 라이브러리 의존, 코어 이벤트를 AG-UI `RunAgentInput`/`BaseEvent`로 변환.
- A2A 어댑터 → 공식 `a2a-python` 라이브러리 의존, 코어 실행을 A2A `Task` 상태 머신으로 노출.
- MCP 어댑터 → MCP 라이브러리 의존, 외부 MCP tool descriptor를 코어 tool 계약으로 정규화 (및 코어 tool을 MCP server로 노출).

채택 이유:

- 프로토콜이 둘 이상이라는 사실 자체가 중립 코어를 **유일 정합**으로 만든다. 셋 중 어느 하나를 코어에 고정하면 나머지가 종속된다.
- 코어 비의존을 유지하여 ADR-0009 검증 기준과 일관된다. 프로토콜 라이브러리 버전 변경은 해당 어댑터에 격리된다.
- pydantic-ai 선례(`ui.ag_ui` 어댑터 + `fasta2a`)와 정확히 일치한다 — 검증된 산업 패턴이다.

실행 루프 소유 축에서는 ADR-0009의 명령형 `execute()` 본문 작성 방식과, 프레임워크가 루프를 소유하고 개발자는 설정만 선언하는 방식을 비교했다. 후자를 채택한다 (아래 "결정" 참조). 명령형 방식은 개발자가 `model.stream()` 소비·tool invoke·approval 분기를 매번 재작성하게 하여 배관 코드 중복과 HITL/compaction/recovery 처리의 비일관을 낳는다.

## 결정 (Decision)

### 1. 프레임워크가 실행 루프를 완전 소유한다 (설정 선언형)

agent 실행 루프(model 호출 → tool call 추출 → tool invoke → 결과 주입 → 종료 판정 반복)는 프레임워크 runner가 소유한다. 개발자는 루프 본문을 작성하지 않고, `@Agent` spec으로 **무엇을** 실행할지만 선언한다 (어떤 model, 어떤 tool, 어떤 정책).

- `execute()` 인터페이스는 유지한다 — `@Agent`는 ADR-0009대로 `@UseCase`와 동격인 호출 가능한 application component다. 다만 개발자가 `execute()` 본문에 model-loop를 직접 작성하는 대신, runner가 spec과 DI graph로부터 표준 실행 루프를 **자동 제공**한다. 개발자가 model-mediated orchestration의 기본 흐름을 넘어서는 커스텀 제어가 필요할 때만 본문을 직접 작성한다.
- 의존성은 ADR-0009대로 생성자 DI로 주입한다. model(`IAgentModel`), tool(`@agent_tool`로 노출된 capability), outbound port는 생성자 인자다. `@Agent` spec은 이 의존성을 다시 선언하지 않는다.
- 이 DX는 pydantic-ai를 참조한다 — 개발자는 비즈니스 의도(model·tool·정책)만 선언하고, 루프 실행은 프레임워크가 제공한다.

### 2. 프로토콜 중립 코어 + 어댑터 분리 (대안 γ)

`core/spakky-agent`는 프로토콜 중립 이벤트 taxonomy와 실행 루프만 소유하고, 외부 프로토콜은 어댑터로 분리한다.

- 어댑터가 프로토콜 라이브러리에 의존한다: AG-UI 어댑터 = `ag_ui`, A2A 어댑터 = 공식 `a2a-python`, MCP 어댑터 = MCP 라이브러리.
- 코어는 어떤 프로토콜 라이브러리에도 의존하지 않는다.

### 3. 중립 이벤트 taxonomy

코어 이벤트 taxonomy는 프로토콜 중립이며 다음 종류를 포함한다. 각 이벤트는 attribution 메타데이터를 함께 운반한다.

- `message` — 메시지 단위 출력.
- `reasoning` — model의 추론(reasoning) 출력.
- `tool-call` — `start` / `args` / `end` / `result` 4단계로 tool 호출 수명주기를 표현한다.
- `run` / `step` — 실행(run)과 그 내부 단계(step) 경계.
- `state` — 실행 상태 변화 (ADR-0009 `AgentState` lifecycle과 정렬).
- `artifact` — 산출물(artifact) 출력.

모든 이벤트는 다음 attribution을 운반한다.

- agent attribution — 어느 agent가 발생시킨 이벤트인지.
- parent link — 위임(delegation) 트리에서 부모 실행으로의 연결 (ADR-0009 parent/child linkage와 정렬).
- conversation id — 멀티턴 대화 식별자.

이 taxonomy는 AG-UI `BaseEvent`로 어댑터에서 매핑 가능하되, A2A/MCP로도 매핑 가능하도록 어느 프로토콜에도 종속되지 않는다. ADR-0009의 public `AgentYield` vocabulary(`Token`/`Progress`/`Tool`/`Evidence`/`Approval`/`Final`/`Error`/`Cancel`)는 본 taxonomy로 일반화·정렬되며, 후속 구현 그룹이 정확한 매핑을 확정한다.

### 4. ModelCapability descriptor + IAgentModel 스트림 계약 확장

model backend마다 지원 능력이 다르므로(reasoning 지원 여부, context window 크기, token counting 지원 여부 등), `IAgentModel`에 `ModelCapability` descriptor를 도입한다.

- `ModelCapability`는 reasoning 지원, `context_window` 크기, token counting 지원 등을 선언한다.
- `IAgentModel` 스트림 계약을 reasoning 이벤트 등으로 확장하되, capability를 지원하지 않는 backend에서는 **graceful degrade**한다 (capability 부재 시 startup fail이 아니라 해당 이벤트 종류를 생략).

### 5. HITL 도구 승인 — 통일된 pause → 승인요청 → resume

도구 승인(HITL)은 ADR-0009 `INTERRUPTED(reason=APPROVAL_REQUIRED)` 모델 위에서 **단일 pause → 승인요청 → resume 흐름**으로 통일한다.

- 실행 루프가 승인 필요 action에서 일시정지(pause)하고, caller에게 승인요청을 노출한 뒤, 승인 signal 수신 시 resume한다.
- AG-UI 어댑터는 이를 deferred tool / `RunAgentInput`(승인 결과를 다음 run 입력으로 주입)으로 노출한다 — pydantic-ai deferred tool approval 선례.
- A2A 어댑터는 이를 `input-required` Task 상태로 노출한다.

코어의 단일 pause/resume 모델을 어댑터가 각 프로토콜의 관용으로 투영하므로, HITL 의미가 프로토콜마다 갈라지지 않는다.

### 6. 세션 / 멀티턴 — 영속 세션 + 클라이언트 주입 이력 둘 다

멀티턴 대화는 두 경로를 모두 지원한다.

- **영속 세션** — 프레임워크가 대화 이력을 영속화하고 `conversation_id`로 이어간다. TaskStore는 spakky 영속성 계약(ADR-0009 repository contribution 모델)을 사용한다.
- **클라이언트 주입 이력** — caller가 이력(message history)을 직접 주입한다 (pydantic-ai `message_history` 인자 선례).

둘 중 하나로 강제하지 않는다 — stateless 클라이언트 주입과 stateful 영속 세션이 둘 다 유효한 소비 형태다.

### 7. Context compaction — pluggable CompactionStrategy 포트 + 내장 전략

context 압축은 교체 가능한(pluggable) `CompactionStrategy` 포트로 모델링한다.

- 포트 형태는 pydantic-ai의 message history processor / `ProcessHistory` capability(`compact_messages`)를 참조한다.
- 프레임워크는 내장(built-in) 기본 전략을 제공한다.
- compaction은 `@Agent` spec에 선언하고 실행 루프가 자동 적용한다 — 개발자가 루프 본문에서 직접 호출하지 않는다.
- ADR-0009 `ContextDigest`(압축 결과를 derived evidence로 append) 모델과 정렬한다 — compaction은 raw evidence를 대체하지 않는다.

### 8. teammate (팀 모드) — `@Agent` spec 선언 + A2A 위임

multi-agent 팀 모드(teammate)는 `@Agent` spec으로 선언한다.

- 로컬 teammate는 로컬 `@Pod`(`@Agent` component)로 해석한다.
- 원격 teammate는 A2A `AgentCard`로 discovery·위임한다.
- 위임은 ADR-0009 delegation building block(`DelegationPacket`/`DelegationResult`) 위에서 A2A 어댑터를 통해 원격으로 확장된다.

### 9. 프레임워크 책임 경계

프레임워크가 소유하는 범위와 소비자(application/UI 개발자) 몫을 명확히 분리한다.

프레임워크 소유:

- building blocks (ADR-0009 model/tool/state/signal/evidence/delegation 등)
- 실행 루프 (본 ADR 결정 1)
- 프로토콜 어댑터 (본 ADR 결정 2)
- 인터페이스/계약 (`@Agent` spec, 이벤트 taxonomy, port)

소비자 몫 (프레임워크 범위 밖):

- 렌더링 / UI — AG-UI 이벤트를 받아 화면에 그리는 것은 클라이언트(소비자)의 책임이다 (ADR-0009 "별도 stream projector service를 제공하지 않는다"의 연장).

### 10. 릴리스

v6.10.0 minor 릴리스로 출시한다. 현재 production 소비자가 없으므로 ADR-0009의 명령형 `execute()` 예시 대비 하드 브레이크를 허용한다.

## 결과 (Consequences)

### 긍정적

- 개발자는 model-loop 배관 코드를 작성하지 않고 `@Agent` spec으로 비즈니스 의도만 선언한다 — pydantic-ai 수준의 DX.
- HITL·세션·compaction이 실행 루프에서 일관 처리되어 재현·복구 가능성이 어댑터/프로토콜 전반에서 균일해진다.
- 코어 비의존이 유지되어 AG-UI·A2A·MCP 스펙 변경이 어댑터에 격리된다. 새 프로토콜 추가는 새 어댑터 추가일 뿐 코어를 건드리지 않는다.
- ADR-0009 building block(state/signal/evidence/delegation/contribution persistence)을 그대로 재사용하며 그 위에 선언형 실행과 프로토콜 경계를 얹는다.

### 부정적

- 프레임워크가 루프를 소유하므로, model-mediated orchestration의 표준 흐름을 벗어나는 커스텀 제어는 spec 확장 또는 본문 직접 작성이라는 별도 escape hatch가 필요하다 — escape hatch 설계 실수가 표현력을 제약할 수 있다.
- 중립 이벤트 taxonomy ↔ 세 프로토콜 매핑을 어댑터마다 정확히 정의해야 하며, taxonomy 누락은 특정 프로토콜에서 표현 불가로 드러난다.
- ADR-0009의 명령형 `execute()` 예시와 하드 브레이크가 발생한다 — 마이그레이션 가이드가 필요하다 (현재 고객 없음으로 비용 수용).

### 중립적

- pydantic-ai는 DX·어댑터 분리의 참조 선례일 뿐 의존 대상이 아니다 — ADR-0009 "Pydantic AI는 첫 구현의 정본이 아니다"와 일관된다.
- 본 ADR은 결정·경계만 박제하며, 정확한 클래스/시그니처(이벤트 taxonomy 필드명, `CompactionStrategy` 포트 시그니처, `ModelCapability` 필드)는 후속 구현 그룹(C·D·E·F)이 코드로 확정한다.

## 검증 기준

- `core/spakky-agent`는 `ag_ui`·`a2a-python`·MCP 라이브러리에 직접 의존하지 않는다.
- AG-UI / A2A / MCP 어댑터가 각각 독립 어댑터로 분리되어 해당 프로토콜 라이브러리에만 의존한다.
- `@Agent` spec 선언만으로(루프 본문 직접 작성 없이) model-mediated 실행이 동작한다.
- HITL 도구 승인이 단일 pause → 승인요청 → resume으로 동작하고, AG-UI deferred tool과 A2A `input-required`로 각각 투영된다.
- 영속 세션과 클라이언트 주입 이력 두 경로 모두로 멀티턴이 동작한다.
- `CompactionStrategy` 포트가 교체 가능하고 내장 전략이 spec 선언으로 자동 적용된다.
- `ModelCapability` 미지원 backend에서 graceful degrade한다.
- 원격 teammate가 A2A `AgentCard`로 discovery·위임된다.

## 참고 자료

- [ADR-0009: Agentic Hexagonal Architecture](0009-agentic-hexagonal-architecture.md)
- [ADR-0010: Feature Contribution Policy](0010-feature-contribution-policy.md)
- [AG-UI Overview](https://docs.ag-ui.com/introduction)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [Model Context Protocol Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [Pydantic AI — AG-UI Adapter (`pydantic_ai.ui.ag_ui`)](https://pydantic.dev/docs/ai/api/pydantic-ai/ag_ui)
- [Pydantic AI — Deferred Tools / Human-in-the-Loop Approval](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools)
- [Pydantic AI — Message History Processors (`compact_messages`)](https://pydantic.dev/docs/ai/api/models/base)
