# ADR-0009: Agentic Hexagonal Architecture

- **상태**: Proposed
- **날짜**: 2026-05-04
- **대체**: 해당 없음
- **선행**: [ADR-0010 Feature Contribution Policy](0010-feature-contribution-policy.md)

## 맥락 (Context)

Spakky Framework에 LLM 기반 agent runtime을 추가하는 방향을 논의했다. 초기 질문은 LangGraph와 Pydantic AI 중 어떤 백플레인을 사용할지, 그리고 Service/Repository 같은 DI Pod를 agent tool로 제공할 수 있는 추상화가 필요한지였다.

논의 중 단순한 `run(prompt) -> response` 형태는 프레임워크 기능으로 충분하지 않다는 결론에 도달했다. Agent 기능은 LLM SDK wrapper가 아니라, 로컬 및 SaaS 환경에서 agentic application을 구성하기 위한 계약과 포트가 되어야 한다.

이 문서는 후속 논의를 재개할 수 있도록 현재까지 합의한 개념, 미결정 사항, 외부 프레임워크 적합성 평가를 보존한다. 이 ADR은 아직 구현 착수 결정을 의미하지 않는다.

2026-05-05 추가 결정: agent persistence와 인프라 plugin 조합 폭증 문제를 먼저 해결하기 위해 [ADR-0010 Feature Contribution Policy](0010-feature-contribution-policy.md)를 ADR-0009의 선행 마일스톤으로 진행한다.

## 결정 동인 (Decision Drivers)

- Agent를 LLM 호출 객체가 아니라 소프트웨어적 실행 주체로 정의해야 한다.
- Spakky의 plugin 구조는 설치된 entry point가 `load_plugins()`에서 자동 활성화되는 모델이다.
- Core 패키지는 구현체를 포함하지 않고 계약과 값 객체만 제공해야 한다.
- 로컬 실행과 SaaS 실행을 모두 표현할 수 있어야 한다.
- API 기반 LLM 호출뿐 아니라 vLLM 같은 self-hosted model provider도 지원해야 한다.
- LangGraph, Pydantic AI, MCP, AG-UI, A2A, multi-agent/team mode를 단일 개념 체계 안에서 다룰 수 있어야 한다.
- Service/Repository/UseCase 등 DI Pod를 agent tool로 노출할 때 권한, side effect, approval, evidence를 통제해야 한다.

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

Agentic Hexagonal Architecture는 agent 실행을 hexagonal architecture의 포트와 어댑터로 모델링한다.

Domain/Application 영역에는 deterministic UseCase뿐 아니라 undeterministic agentic execution이 존재할 수 있다. 다만 Agent 자체를 억지로 UseCase의 subclass로 보지 않는다. Agent는 목표 수렴 상태머신이며, application layer는 Agent에게 goal을 위임할 수 있다.

포트 구분:

- **Inbound ports**: agent execution을 시작, 제어, 관찰하는 입력면
- **Outbound ports**: LLM model, tool, memory, checkpoint, message bus, artifact store, remote worker 등 agent가 세계와 상호작용하는 출력면

Adapter 예시:

- Inbound: FastAPI, Typer, WebSocket, AG-UI, MCP Apps, A2A, SaaS control API
- Outbound: LangGraph, Pydantic AI, OpenAI, Anthropic, vLLM, MCP tools, SQLAlchemy store, local/remote worker

## 계약 후보

Core contract 후보:

- `Agent`
- `AgentDefinition`
- `AgentTaskSpec`
- `AgentGoal`
- `AgentState`
- `AgentPhase`
- `AgentExecution`
- `AgentExecutionTrace`
- `AgentAction`
- `AgentObservation`
- `AgentPlan`
- `PlanStep`
- `AgentPolicy`
- `AgentHarness`
- `AgentTool`
- `AgentToolDescriptor`
- `AgentToolRegistry`
- `AgentEvidence`
- `EvidenceRequirement`
- `AcceptanceCriterion`
- `AgentEvaluator`
- `ConvergenceDecision`
- `AgentInterrupt`
- `AgentApproval`
- `AgentTeam`
- `AgentMessageBus`
- `AgentCheckpointStore`
- `AgentEvidenceStore`
- `AgentTraceSink`
- `AgentArtifactStore`

LLM contract 후보:

- `ILLMProvider`
- `IChatModel`
- `ModelRef`
- `ModelCapabilities`
- `ModelRoutingPolicy`
- `ModelUsage`
- streaming invocation events

Core에는 구현체를 두지 않는다. 예를 들어 `InMemoryAgentStateStore`, `FileAgentCheckpointStore`, `DefaultAgentRuntime` 같은 구현체는 core에 존재할 수 없다.

## 하네스와 strict contract

자연어 지시를 그대로 실행 단위로 사용하면 strict한 프레임워크 계약이 성립하지 않는다. 따라서 자연어는 다음 파이프라인으로 다룬다.

```text
Natural Language Intent
  -> AgentTaskSpec
  -> AgentExecutionPlan
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

## Multi-Agent / Team Mode

Agent system은 단일 subagent 위임뿐 아니라 Claude team mode와 유사한 multi-agent collaboration을 지원해야 한다.

구분:

- **Subagent**: 특정 작업을 위임받는 실행 단위
- **Teammate**: team identity, parent session, mailbox/message bus, permission delegation, plan approval, lifecycle을 가진 협업 구성원
- **Team runtime**: 여러 agent 실행을 spawn, route, inspect, pause, resume, cancel하는 control plane

Claude Code 참고 관찰:

- Agent definition은 prompt, tools, disallowed tools, model, MCP servers, skills, max turns, background, memory, effort, permission mode를 포함한다.
- Skill은 frontmatter로 allowed tools, model, agent, effort, hooks, fork context 등을 정의한다.
- Team mode는 teammate identity, parent session, mailbox, permission delegation, plan approval, lifecycle을 별도 관리한다.
- Swarm backend는 tmux, iTerm2, in-process를 분리한다.

Spakky에서는 이를 특정 terminal backend에 묶지 않고 `AgentMessageBus`, `AgentTeamRuntime`, `AgentWorkerBackend` 같은 포트로 일반화한다.

## 외부 프레임워크 적합성

LangGraph/LangChain:

- 6단계 lifecycle을 `StateGraph` node와 graph state로 매핑하기 좋다.
- checkpoint/resume, interrupt, human-in-the-loop, streaming, multi-agent graph에 적합하다.
- canonical AgentExecution state machine 구현의 기준 adapter 후보로 적합하다.

Pydantic AI:

- typed tools, Pydantic model 기반 structured output, toolset composition, MCP, durable execution과 잘 맞는다.
- `AgentTaskSpec`, `AgentEvidence`, `ConvergenceDecision` 같은 strict contract 구현에 특히 적합하다.
- 필요하면 pydantic-graph로 canonical state machine을 구현할 수 있다.

역할 구분:

- `spakky-langgraph`: state-machine-first execution adapter
- `spakky-pydantic-ai`: typed-contract-first execution adapter
- `spakky-vllm`: local/self-hosted model provider adapter
- `spakky-agent-*`: inbound/outbound protocol adapters

## 고려한 대안 (Considered Options)

### 대안 A: 단일 LLM SDK wrapper

`run(prompt) -> response` 형태의 단순 실행 API를 제공한다.

장점:

- 구현 범위가 작다.
- 학습 비용이 낮다.

단점:

- Spakky plugin으로서 차별점이 약하다.
- tool governance, checkpoint, team mode, evidence, SaaS-ready 요구를 담기 어렵다.
- LangGraph/Pydantic AI의 고유 장점을 추상화 과정에서 잃는다.

### 대안 B: Agentic Hexagonal Architecture 계약

Agent를 목표 수렴 상태머신으로 정의하고, inbound/outbound 포트와 adapter로 실행한다.

장점:

- 로컬/SaaS, LangGraph/Pydantic AI, MCP/AG-UI/A2A를 같은 구조로 다룰 수 있다.
- Service/Repository toolization을 Spakky DI와 연결할 수 있다.
- evidence/evaluator 기반 strict contract를 설계할 수 있다.

단점:

- 초기 설계 범위가 크다.
- DI의 복수 구현체 선택 문제가 먼저 해결되어야 한다.
- execution adapter와 persistence adapter의 조합 복잡도가 높다.

## 결정 (Decision)

현재 논의의 기준점으로 대안 B를 채택한다. 다만 이 ADR은 `Proposed` 상태이며, 실제 구현 마일스톤은 DI multi-implementation resolution 이후 다시 구체화한다.

## 결과 (Consequences)

### 긍정적

- Agent를 LLM wrapper가 아닌 runtime entity로 모델링할 수 있다.
- 백플레인 교체 가능성을 추상화 주장으로 끝내지 않고 adapter 계약으로 검증할 수 있다.
- 하네스, evidence, evaluator, team collaboration을 일관된 개념 체계에 넣을 수 있다.

### 부정적

- 현재 DI 컨테이너의 복수 구현체 ambiguity 문제가 agent plugin 조합을 막는다.
- Core contract와 adapter package 수가 늘어난다.
- 설계 검증을 위해 conformance test가 필요하다.

### 중립적

- Agent 하네스의 런타임 정본은 Python annotation/class 기반으로 두고, Markdown/YAML 기반 하네스는 공유/패키징/import-export 표면으로 둔다.
- 실제 SaaS 구현은 Spakky Framework 범위 밖이다. Framework는 SaaS-ready port만 제공한다.

## 미결정 사항

- Agent contract의 정확한 Python API
- execution adapter와 persistence adapter의 plugin packaging
- AG-UI/MCP/A2A inbound adapter를 같은 마일스톤에 포함할지 여부
- evidence/evaluator conformance test 수준
- vLLM adapter를 직접 구현할지, OpenAI-compatible provider로 일반화할지 여부
- Agent team runtime의 최소 필수 계약

## 참고 자료

- `~/projects/claude-code/src/entrypoints/sdk/coreSchemas.ts`
- `~/projects/claude-code/src/tools/AgentTool/loadAgentsDir.ts`
- `~/projects/claude-code/src/tools/AgentTool/runAgent.ts`
- `~/projects/claude-code/src/utils/teammate.ts`
- `~/projects/claude-code/src/utils/teammateContext.ts`
- `~/projects/claude-code/src/utils/teammateMailbox.ts`
- `~/projects/claude-code/src/utils/swarm/backends/types.ts`
- LangGraph persistence, interrupts, human-in-the-loop documentation
- Pydantic AI agent, toolset, MCP, durable execution documentation
