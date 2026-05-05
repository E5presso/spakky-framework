# ADR-0009: Agentic Hexagonal Architecture

- **상태**: Accepted
- **날짜**: 2026-05-04
- **갱신**: 2026-05-05
- **대체**: 해당 없음
- **선행 완료**: [ADR-0010 Feature Contribution Policy](0010-feature-contribution-policy.md)

## 맥락 (Context)

Spakky Framework에 LLM 기반 agent runtime을 추가하는 방향을 논의했다. 초기 질문은 LangGraph와 Pydantic AI 중 어떤 백플레인을 사용할지, 그리고 Service/Repository 같은 DI Pod를 agent tool로 제공할 수 있는 추상화가 필요한지였다.

논의 중 단순한 `run(prompt) -> response` 형태는 프레임워크 기능으로 충분하지 않다는 결론에 도달했다. Agent 기능은 LLM SDK wrapper가 아니라, 로컬 및 SaaS 환경에서 agentic application을 구성하기 위한 계약, orchestration, policy, evidence, persistence port가 되어야 한다.

이 ADR은 더 이상 후속 논의 메모가 아니다. ADR-0010이 완료되었으므로, ADR-0009는 구현 가능한 단일 마일스톤 스펙으로 확정한다.

마일스톤은 쪼개지 않는다. 하나의 완전한 마일스톤은 다음을 모두 포함한다.

- `core/spakky-agent`의 모든 public contract
- agent lifecycle을 실제로 구동하는 core orchestration과 policy
- typed execution backplane adapter
- durable checkpoint/evidence/artifact persistence contribution
- DI Pod toolization
- streaming/interrupt/approval/resume/cancel/evaluate/team execution 유즈케이스
- conformance test와 user/developer documentation

## 결정 동인 (Decision Drivers)

- Agent를 LLM 호출 객체가 아니라 소프트웨어적 실행 주체로 정의해야 한다.
- Core는 저수준 인프라 구현을 포함하지 않지만, 사용자 DX 표면, orchestration, policy, lifecycle, convergence 같은 고수준 로직은 소유해야 한다.
- Core feature는 항상 plugin을 통한 간접 설치를 전제로 한다. 따라서 기본 in-memory persistence 구현은 제공하지 않는다.
- Agent persistence는 optional nice-to-have가 아니라 checkpoint/resume/evidence/replay를 위한 필수 계약이다.
- Feature Contribution Policy를 통해 `spakky-sqlalchemy` 같은 인프라 plugin이 `spakky-agent` persistence 구현을 기여해야 한다.
- Service/Repository/UseCase 등 DI Pod를 agent tool로 노출할 때 권한, side effect, approval, evidence를 통제해야 한다.
- 로컬 실행과 SaaS 실행을 모두 표현할 수 있어야 한다. 단, SaaS 제품 구현은 Framework 범위 밖이며 SaaS-ready port만 제공한다.
- API 기반 모델 호출뿐 아니라 vLLM 같은 self-hosted OpenAI-compatible endpoint도 설정으로 연결 가능해야 한다.
- AG-UI, MCP, A2A 같은 agent protocol을 특정 adapter 패키지 폭증 없이 같은 event/task/artifact 개념 체계 안에서 표현할 수 있어야 한다.

## 핵심 정의

Spakky에서 Agent는 LLM wrapper가 아니다.

> Agent는 지시사항 분석, 맥락 파악, 도구 선정, 실행 계획 수립, 실행, 실행 결과 평가를 초기 목표에 부합할 때까지 반복하여 실행 결과를 요구사항에 수렴시키는 목표 수렴 상태머신이다.

이 정의에서 LLM은 Agent 자체가 아니라 다음 행동을 선택하는 decision backplane 중 하나다.

Canonical lifecycle:

1. **Instruction Analysis**: 지시, 목표, 제약, 완료 조건을 해석한다.
2. **Context Acquisition**: 현재 상태, 환경, memory, 사용 가능한 tool을 파악한다.
3. **Tool Selection**: 목표 달성에 필요한 action surface를 고른다.
4. **Plan Construction**: 실행 순서, 중단 조건, 검증 방법, fallback을 세운다.
5. **Execution**: tool 호출, subagent 위임, 사용자 질의, 외부 시스템 변경을 수행한다.
6. **Evaluation**: 실행 결과가 목표, 요구사항, 정책, 품질 기준에 수렴했는지 평가한다.
7. **Iteration or Termination**: 부족하면 상태를 갱신하고 반복한다. 충분하면 결과와 trace를 확정한다.

## Agentic Hexagonal Architecture

Agentic Hexagonal Architecture는 agent 실행을 hexagonal architecture의 포트와 adapter로 모델링한다.

Domain/Application 영역에는 deterministic UseCase뿐 아니라 undeterministic agentic execution이 존재할 수 있다. 다만 Agent 자체를 억지로 UseCase의 subclass로 보지 않는다. Agent는 목표 수렴 상태머신이며, application layer는 Agent에게 goal을 위임할 수 있다.

포트 구분:

- **Inbound ports**: agent execution을 시작, 제어, 관찰하는 입력면
- **Outbound ports**: decision backplane, model provider, tool executor, memory, checkpoint store, evidence store, artifact store, message bus, worker backend 등 agent가 세계와 상호작용하는 출력면

Adapter 구분:

- **Core runtime**: `AgentRuntime`, `AgentExecutionService`, `AgentPolicyEngine`, `AgentToolRegistry`, `AgentEvaluatorPipeline`, `AgentTeamRuntime`
- **Execution backplane adapter**: Pydantic AI 기반 typed agent 실행
- **Persistence contribution**: SQLAlchemy 기반 checkpoint/evidence/artifact/run state 저장
- **Protocol adapter**: AG-UI, MCP, A2A, FastAPI, Typer 같은 외부 노출면. 첫 마일스톤에서는 별도 `spakky-agent-*` 패키지로 만들지 않고, core event/task/artifact DTO가 protocol mapping 가능한 shape를 제공한다.

## Core Responsibility

`core/spakky-agent`는 다음을 포함한다.

- public value objects와 interfaces
- agent definition/harness DX
- instruction-to-task normalization
- lifecycle state machine
- policy enforcement
- approval/interrupt/resume orchestration
- tool registry와 DI Pod toolization metadata
- evidence requirement와 convergence evaluation pipeline
- team/subagent coordination contract와 local orchestration
- streaming event model
- persistence port 호출 순서와 transaction boundary policy
- conformance test fixture와 fake port test double

Core가 포함하지 않는 것:

- 외부 LLM SDK 직접 호출
- DB table/ORM/session 구현
- 파일 시스템, Redis, SQLAlchemy 같은 저수준 저장소 구현
- FastAPI/Typer/MCP/A2A 서버 구현
- vendor-specific API client

따라서 `DefaultAgentRuntime` 같은 고수준 orchestration 구현은 core에 둘 수 있다. 반대로 `InMemoryAgentCheckpointStore`, `FileAgentArtifactStore`, `SqlAlchemyAgentRunStore` 같은 저장소 구현은 core에 둘 수 없다.

## Package Decision

첫 구현 마일스톤은 다음 패키지만 만든다.

| 패키지 | 역할 |
|------|------|
| `core/spakky-agent` | Agent contract, runtime orchestration, policy, approval, evidence, convergence, team runtime, persistence ports |
| `plugins/spakky-pydantic-ai` | Pydantic AI 기반 reference execution backplane adapter |
| `plugins/spakky-sqlalchemy` contribution | `spakky.contributions.spakky.agent`로 agent durable state/checkpoint/evidence/artifact store 구현 기여 |

명시적으로 만들지 않는 패키지:

| 패키지 | 결정 |
|------|------|
| `core/spakky-llm` | 만들지 않는다. 모델 호출 추상화는 agent execution backplane port 안에 둔다. LangChain/Pydantic AI가 이미 제공하는 model abstraction을 중복하지 않는다. |
| `plugins/spakky-vllm` | 만들지 않는다. vLLM은 OpenAI-compatible endpoint 설정으로 연결한다. 별도 adapter가 필요한 근거가 생기기 전까지 Pydantic AI/OpenAI-compatible model config로 충분하다. |
| `plugins/spakky-langgraph` | 첫 구현에 포함하지 않는다. LangGraph는 graph-first advanced adapter 후보로 남기되, reference adapter는 Pydantic AI 하나로 고정한다. |
| `plugins/spakky-agent-fastapi` | 만들지 않는다. 기존 `spakky-fastapi` 빌딩 블록으로 application이 inbound adapter를 작성한다. |
| `plugins/spakky-agent-typer` | 만들지 않는다. 기존 `spakky-typer` 빌딩 블록으로 application이 CLI adapter를 작성한다. |
| `plugins/spakky-agent-mcp` | 만들지 않는다. 첫 마일스톤은 MCP outbound tool 사용과 core event/tool schema까지만 다룬다. |
| `plugins/spakky-agent-a2a` | 만들지 않는다. A2A task/artifact mapping을 고려한 DTO를 제공하되 protocol server adapter는 별도 패키지로 분리하지 않는다. |
| `plugins/spakky-agent-sqlalchemy` | 만들지 않는다. SQLAlchemy 구현은 ADR-0010 contribution으로 `plugins/spakky-sqlalchemy`에 둔다. |

## Public Contract

`core/spakky-agent`는 다음 contract를 제공한다. 이름은 구현 중 Python naming convention에 맞춰 조정할 수 있지만, 의미와 책임은 유지한다.

### Definition

- `AgentDefinition`
- `AgentHarness`
- `AgentInstruction`
- `AgentGoal`
- `AgentTaskSpec`
- `AgentCapability`
- `AgentSkill`
- `AgentModelProfile`
- `AgentRuntimeOptions`

### Execution

- `AgentExecutionService`
- `AgentRuntime`
- `AgentRun`
- `AgentRunId`
- `AgentRunStatus`
- `AgentPhase`
- `AgentState`
- `AgentCheckpoint`
- `AgentExecutionTrace`
- `AgentEvent`
- `AgentEventStream`

### Planning And Action

- `AgentPlan`
- `PlanStep`
- `AgentAction`
- `AgentObservation`
- `AgentActionResult`
- `AgentIteration`
- `AgentTerminationReason`

### Toolization

- `AgentTool`
- `AgentToolDescriptor`
- `AgentToolRegistry`
- `ToolCall`
- `ToolResult`
- `ToolEffect`
- `ToolRiskLevel`
- `ToolPolicy`
- `PodToolFactory`

### Policy And Approval

- `AgentPolicy`
- `AgentPolicyEngine`
- `ApprovalPolicy`
- `AgentInterrupt`
- `ApprovalRequest`
- `ApprovalDecision`
- `AgentPermission`
- `AgentActor`

### Evidence And Evaluation

- `AgentEvidence`
- `EvidenceRequirement`
- `AcceptanceCriterion`
- `AgentEvaluator`
- `EvaluatorPipeline`
- `ConvergenceDecision`
- `SemanticEvaluationRequest`
- `DeterministicEvaluationResult`

### Persistence Ports

- `IAgentRunStore`
- `IAgentCheckpointStore`
- `IAgentEvidenceStore`
- `IAgentArtifactStore`
- `IAgentMessageStore`
- `IAgentLockStore`

### Backplane Ports

- `IAgentDecisionBackplane`
- `IAgentModelRouter`
- `AgentBackplaneRequest`
- `AgentBackplaneResponse`
- `AgentModelUsage`
- `AgentStreamChunk`

### Team Runtime

- `AgentTeam`
- `AgentTeamRuntime`
- `AgentWorker`
- `AgentWorkerBackend`
- `AgentMailbox`
- `AgentMessage`
- `AgentDelegation`
- `AgentDelegationPolicy`

## Strict Contract Pipeline

자연어 지시를 그대로 실행 단위로 사용하면 strict한 프레임워크 계약이 성립하지 않는다. 따라서 자연어는 다음 파이프라인으로 다룬다.

```text
Natural Language Intent
  -> AgentTaskSpec
  -> AgentPlan
  -> AgentAction / AgentObservation
  -> AgentEvidence
  -> ConvergenceDecision
```

Agent의 자연어 출력은 결과가 아니다. Agent가 남긴 evidence와 evaluator의 convergence decision이 결과다.

Evaluator는 다음 층으로 분리한다.

- Policy evaluator
- Trace evaluator
- Deterministic evaluator
- Semantic evaluator
- Human approval evaluator

Semantic evaluator는 필요하지만 deterministic/policy/trace evaluator와 명시적으로 구분한다.

## Tool Governance

DI Pod를 agent tool로 노출하려면 명시적 metadata가 필요하다. 모든 tool은 다음 속성을 선언한다.

- stable tool name
- input/output schema
- side effect classification
- read/write scope
- required permission
- approval requirement
- idempotency hint
- timeout/retry policy
- evidence emission rule

기본값은 보수적이어야 한다. metadata가 없는 임의 Pod method를 자동 tool로 공개하지 않는다.

Tool 실행은 `AgentPolicyEngine`을 통과해야 하며, write side effect가 있는 tool은 기본적으로 approval 또는 명시적 policy grant가 필요하다.

## Persistence And Contribution

Agent runtime은 durable persistence 없이 complete로 간주될 수 없다. SQLAlchemy 구현은 `plugins/spakky-sqlalchemy`가 feature contribution으로 제공한다.

```toml
[project.optional-dependencies]
agent = ["spakky-agent>=6.5.0"]

[project.entry-points."spakky.contributions.spakky.agent"]
spakky-sqlalchemy = "spakky.plugins.sqlalchemy.contributions.agent:initialize"
```

Contribution은 다음 구현을 등록한다.

- `AgentRunTable`
- `AgentCheckpointTable`
- `AgentEvidenceTable`
- `AgentArtifactTable`
- `AgentMessageTable`
- `SqlAlchemyAgentRunStore`
- `SqlAlchemyAgentCheckpointStore`
- `SqlAlchemyAgentEvidenceStore`
- `SqlAlchemyAgentArtifactStore`
- `SqlAlchemyAgentMessageStore`
- `SqlAlchemyAgentLockStore`

`spakky-sqlalchemy` base plugin은 `spakky-agent` 설치 여부를 감지하지 않는다. `spakky-agent`가 active feature이고 `spakky-sqlalchemy` provider가 active일 때 loader가 contribution을 호출한다.

## Execution Backplane Decision

Reference execution adapter는 `plugins/spakky-pydantic-ai`로 결정한다.

선정 근거:

- Pydantic AI는 typed output validation, reusable agent, streaming/event/iteration run mode를 제공한다.
- Pydantic AI durable execution 문서는 long-running, asynchronous, human-in-the-loop, restart/failure recovery use case를 명시적으로 다룬다.
- Pydantic AI는 MCP와 durable execution을 함께 다룰 수 있다.
- Spakky의 strict contract는 `AgentTaskSpec`, `AgentEvidence`, `ConvergenceDecision` 같은 Pydantic model 중심의 typed boundary와 잘 맞는다.

LangGraph는 이번 마일스톤의 reference adapter로 선택하지 않는다.

- LangGraph는 checkpoint, interrupt, human-in-the-loop, time travel, fault tolerance가 강한 graph-first runtime이다.
- 그러나 첫 마일스톤에서 Pydantic AI와 LangGraph를 동시에 구현하면 adapter conformance보다 adapter 간 feature parity가 중심 과제가 된다.
- LangChain agent abstraction도 LangGraph 기반 durable runtime 방향으로 수렴하고 있으므로, LangGraph는 향후 advanced graph adapter 후보로 충분히 남길 수 있다.

vLLM은 별도 adapter로 선택하지 않는다.

- vLLM은 OpenAI-compatible server를 제공하므로 Pydantic AI/OpenAI-compatible model configuration으로 연결한다.
- Spakky가 vLLM 전용 scheduling, batching, deployment, GPU control plane을 소유하지 않는 한 `spakky-vllm`은 불필요한 wrapper다.

## Protocol Boundary

첫 마일스톤은 protocol adapter 패키지를 만들지 않는다. 대신 core event/task/artifact model이 다음 protocol로 자연스럽게 mapping되도록 설계한다.

- AG-UI: streaming event, user intent, approval, cancel/resume event mapping
- MCP: tool descriptor, tool call/result, resource/artifact link mapping
- A2A: task, task status, message, artifact, streaming task update mapping

Framework 사용자는 기존 `spakky-fastapi`, `spakky-typer`, `spakky-grpc` 빌딩 블록으로 inbound adapter를 작성할 수 있어야 한다. 별도 `spakky-agent-fastapi` 같은 package는 만들지 않는다.

## Required Use Cases

마일스톤은 다음 유즈케이스를 모두 실제 실행 가능하게 만든다.

1. Python code에서 `AgentDefinition`을 선언하고 DI container에 등록한다.
2. 자연어 instruction을 `AgentTaskSpec`으로 normalize한다.
3. Agent run을 시작하고 run id/status/current phase를 조회한다.
4. Agent event stream을 구독해 plan/action/observation/evidence/status 변경을 받는다.
5. DI Pod method를 명시적 metadata 기반 tool로 등록하고 실행한다.
6. Tool policy가 read/write/side effect/permission/approval requirement를 판정한다.
7. Approval이 필요한 action에서 run을 interrupt하고, 승인/거절 후 resume한다.
8. Run checkpoint를 저장하고 process restart 이후 resume한다.
9. Evidence와 artifact를 저장하고 evaluator가 convergence decision을 만든다.
10. Run을 cancel/fail/timeout 처리하고 terminal state를 저장한다.
11. Subagent에게 bounded task를 위임하고 mailbox/event stream으로 결과를 수집한다.
12. Team runtime이 worker spawn, message route, pause/resume/cancel을 수행한다.
13. Pydantic AI backplane이 typed output, streaming, tool call을 Spakky contract로 변환한다.
14. SQLAlchemy contribution이 run/checkpoint/evidence/artifact/message/lock store를 제공한다.
15. OpenAI-compatible endpoint 설정으로 self-hosted vLLM server를 사용할 수 있다.

## Considered Options

### 대안 A: 단일 LLM SDK wrapper

`run(prompt) -> response` 형태의 단순 실행 API를 제공한다.

장점:

- 구현 범위가 작다.
- 학습 비용이 낮다.

단점:

- Spakky plugin으로서 차별점이 약하다.
- tool governance, checkpoint, team mode, evidence, SaaS-ready 요구를 담기 어렵다.
- LangGraph/Pydantic AI의 고유 장점을 추상화 과정에서 잃는다.

### 대안 B: Adapter 다중 구현 동시 제공

`spakky-pydantic-ai`, `spakky-langgraph`, `spakky-vllm`, `spakky-agent-fastapi`, `spakky-agent-typer`, `spakky-agent-mcp`, `spakky-agent-a2a`, `spakky-agent-sqlalchemy`를 모두 만든다.

장점:

- 프로토콜과 백플레인별 선택지가 많다.
- 외형상 완전해 보인다.

단점:

- 패키지 수가 폭증한다.
- 첫 마일스톤의 중심이 core contract가 아니라 adapter matrix가 된다.
- inbound adapter는 framework 사용자가 기존 FastAPI/Typer/gRPC 빌딩 블록으로 작성할 수 있는 영역까지 과도하게 포장한다.
- `spakky-agent-sqlalchemy`는 ADR-0010의 contribution policy와 충돌한다.

### 대안 C: Core-complete + single reference adapter + contribution persistence

`core/spakky-agent`에 모든 고수준 contract와 runtime orchestration을 두고, Pydantic AI reference adapter와 SQLAlchemy contribution persistence만 함께 구현한다.

장점:

- 하나의 마일스톤 안에서 모든 agent contract와 실제 실행 유즈케이스를 완성할 수 있다.
- adapter package 폭증 없이 실행 가능한 기준 구현을 제공한다.
- ADR-0010과 일관된다.
- 이후 adapter 추가 여부는 contract conformance 문제로 축소된다.

단점:

- core scope가 크다.
- Pydantic AI adapter 품질이 reference behavior의 기준이 되므로 conformance test가 촘촘해야 한다.
- Protocol server adapter는 첫 화면의 편의 기능이 아니라 application integration responsibility로 남는다.

## 결정 (Decision)

대안 C를 채택한다.

ADR-0009 마일스톤은 `core/spakky-agent`, `plugins/spakky-pydantic-ai`, `plugins/spakky-sqlalchemy`의 `spakky-agent` contribution을 하나의 완성 단위로 구현한다.

이 마일스톤은 “agent framework의 foundation”이 아니라 “Spakky에서 agentic application을 실제로 작성하고 실행할 수 있는 완성 기능”이어야 한다.

## 결과 (Consequences)

### 긍정적

- Agent를 LLM wrapper가 아닌 runtime entity로 모델링할 수 있다.
- Core가 DX, orchestration, policy, convergence를 소유하므로 Spakky다운 프레임워크 표면이 생긴다.
- 백플레인 교체 가능성을 추상화 주장으로 끝내지 않고 Pydantic AI reference adapter와 conformance test로 검증할 수 있다.
- SQLAlchemy persistence는 ADR-0010 contribution으로 제공되어 plugin 폭증을 막는다.
- AG-UI/MCP/A2A는 DTO/event shape로 고려하되 별도 package 폭증을 만들지 않는다.

### 부정적

- 단일 마일스톤이 크고 ambitious하다.
- Core contract 설계 실수가 이후 adapter 생태계 전체에 영향을 준다.
- Team runtime까지 포함하므로 acceptance test 설계가 어렵다.

### 중립적

- Agent 하네스의 런타임 정본은 Python annotation/class 기반으로 두고, Markdown/YAML 기반 하네스는 공유/패키징/import-export 표면으로 둔다.
- 실제 SaaS 구현은 Spakky Framework 범위 밖이다. Framework는 SaaS-ready port만 제공한다.
- LangGraph adapter는 선택하지 않았지만 배제하지 않는다.

## 검증 기준

- `core/spakky-agent`는 외부 LLM SDK, DB, protocol server에 직접 의존하지 않는다.
- `core/spakky-agent`는 고수준 runtime orchestration과 policy implementation을 포함한다.
- `plugins/spakky-pydantic-ai` 없이 core contract import와 unit test가 가능하다.
- `plugins/spakky-pydantic-ai`가 typed output, streaming, tool call, semantic evaluation을 Spakky contract로 변환한다.
- `plugins/spakky-sqlalchemy` base plugin은 `spakky-agent` 설치 여부를 감지하지 않는다.
- `plugins/spakky-sqlalchemy`는 `spakky.contributions.spakky.agent` entry point로 agent persistence 구현을 기여한다.
- `load_plugins(include=...)`에서 `spakky-agent`와 `spakky-sqlalchemy`가 모두 active일 때만 SQLAlchemy agent contribution이 로드된다.
- approval interrupt 후 process restart/resume 시나리오가 통과한다.
- tool side effect policy와 evidence requirement가 테스트로 검증된다.
- team runtime의 worker spawn/message route/cancel/resume이 테스트로 검증된다.
- OpenAI-compatible endpoint config로 vLLM server를 사용할 수 있음을 adapter 설정 테스트로 검증한다.

## 티켓화 기준

이 ADR 직후 생성되는 GitHub Issues는 조사 티켓이 아니라 구현 티켓이어야 한다. 기술 선택은 본 ADR에서 완료되었다.

티켓은 다음 축을 모두 포함해야 한다.

- `core/spakky-agent` package skeleton과 public contract
- runtime lifecycle state machine
- policy/approval/interrupt/resume
- tool registry와 DI Pod toolization
- evidence/evaluator/convergence
- persistence port와 SQLAlchemy contribution
- Pydantic AI backplane adapter
- team runtime과 mailbox
- event stream/protocol-shape DTO
- conformance tests
- README, guide, API docs, ARCHITECTURE sync

## 참고 자료

- [ADR-0010: Feature Contribution Policy](0010-feature-contribution-policy.md)
- [Pydantic AI Agents](https://pydantic.dev/docs/ai/core-concepts/agent/)
- [Pydantic AI Durable Execution](https://pydantic.dev/docs/ai/integrations/durable_execution/overview/)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/stable/getting_started/quickstart/#openai-compatible-server)
- [Model Context Protocol Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [AG-UI Overview](https://docs.ag-ui.com/introduction)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
