# spakky-agent

> `spakky-agent`는 Agent workflow를 Spakky 컴포넌트로 모델링하기 위한 계약, 도구, 상태, signal, evidence 타입을 제공합니다.

Agentic Hexagonal Architecture의 core 계약입니다.

## 설치

```bash
pip install spakky-agent
```

`spakky-agent`는 `@Agent`, `AgentExecutionSpec`, `RunAgentInput`, `AgentRunner`,
`AgentEvent`, `AgentYield`, retrieval/memory, offline evaluation, pricing/telemetry, tool
dispatch, context compaction, state/signal/evidence repository port, task store,
safety/recovery/delegation 타입 같은 public contract를
소유합니다. 이 패키지는 의도적으로 LLM provider SDK, SQLAlchemy, FastAPI, Typer,
AG-UI, A2A, MCP를 import하지 않습니다. 운영에서 durable execution을 사용하려면 provider
contribution의 repository 구현이 필요하며, 운영용 in-memory fallback은 제공하지
않습니다.

## Bounded iterative runner

`execute()`를 생략한 `@Agent`에는 framework-owned iterative loop가 합성됩니다. 각 model
step은 terminal response와 whole tool batch를 모은 뒤 catalog/ID/signature/authority를
전부 검증합니다. Gate가 열리면 tool을 순차 dispatch하고 assistant tool-call message와
`TOOL` result message를 history에 추가해 다음 model step을 호출합니다. Tool call이 없는
valid terminal step에서 `FINAL` 또는 `RUN_FINISHED`를 정확히 한 번 방출합니다.

`AgentExecutionSpec.limits`의 타입은 `AgentExecutionLimits`이며 default는 다음과 같습니다.

| 필드 | 기본값 | 집행 시점 |
| --- | --- | --- |
| `max_steps` | `8` | 다음 model request 직전 |
| `max_tool_calls` | `32` | candidate batch 전체 dispatch 직전 |
| `max_tokens` | `None` | 각 terminal provider usage 누적 직후 |
| `max_cost` | `None` | pricing이 계산한 각 terminal model step cost 누적 직후 |
| `timeout_seconds` | `None` | model과 async tool await의 invocation deadline |

`AgentExecutionSpec.timeout_seconds` alias는 없습니다. `max_tokens`가 설정됐지만 provider가
`ModelUsage.total_tokens`를 주지 않으면 `agent_usage_unavailable`로 fail closed합니다.
`max_cost`는 positive `Decimal`만 허용하며 operator `ModelPricingCatalog`가 없으면 첫 model
request 전에 `agent_cost_unavailable`입니다.
Streaming path와 `NO_STREAM_UNTIL_FINAL_GUARDED`의 `complete()` path는 같은 batch,
authority, history, limit, terminal uniqueness 의미를 사용합니다.

Deadline이 있는 batch에 in-process sync tool이 포함되면 timeout을 실행 중 강제할 수
없으므로 runner가 전체 batch를 호출 전에 `agent_sync_tool_timeout_unenforceable`로
거부합니다. Async tool만 actual timeout 경계 안에서 실행됩니다.

Approval checkpoint는 call ID만 저장하지 않고
`approval:{state_id}:{call_id}:{digest}` fingerprint를 저장합니다. `digest`는 canonical
JSON argument에 대한 full SHA-256이므로 persisted argument가 바뀌면 기존 승인을
재사용하지 않습니다. `MODIFY` 성공 시 pending call과 assistant `tool_calls` history 모두
최종 approved arguments로 교체됩니다.

Candidate-only provider stream은 `run_events()`가 missing tool START/END frame만 합성합니다.
Signal hook의 `Progress` yield는 event surface에서 `ArtifactEvent(name="signal_progress")`가
되며 다른 yield shape는 `agent_signal_projection_unsupported`로 fail closed합니다.

Compaction은 assistant tool-call과 모든 correlated `TOOL` results를 하나의 group으로
보존합니다. Runner는 입력과 각 custom strategy 출력 직후 correlation을 검증하며 orphan
또는 incomplete group은 provider 호출 전에 `agent_model_execution_failed`로 종료합니다.

Protocol-neutral event step은 `model-N`, 실제 tool dispatch는 `tool-N`입니다. Message/reasoning ID와
missing tool-call ID도 model step과 batch index를 포함합니다. Step metadata와 durable
model evidence는 누적 model/tool/token counter, provider usage, 제공된 actual route
`model_ref`/`profile`/`provider`/`model`을 보존합니다. Protocol projector가 이 metadata
전체를 wire에 보존한다는 의미는 아닙니다.

Token budget failure도 현재 step의 route/usage/counters를 terminal metadata에 보존하고,
durable path에서는 동일 snapshot과 typed error를 model-decision evidence로 남깁니다.

## Model selection과 capability

Core의 run-scoped 선택 계약은 logical ref 하나뿐입니다.

```python
from spakky.agent import ModelSelection, RunAgentInput


run_input = RunAgentInput(
    state_id="run-42",
    instruction="요청을 분류해 주세요.",
    model_selection=ModelSelection(model_ref="support/primary"),
)
```

`ModelSelection`은 frozen dataclass이며 필수 `model_ref: str` 외에 provider, profile,
physical model, metadata field를 두지 않습니다. Blank ref는 `AgentDefinitionError`입니다.
Runner는 selection을 `ModelRequest`와 `IAgentModel.capability_for()`에 전달합니다. 고정
model adapter는 같은 capability를 반환할 수 있고, `spakky-llm` 같은 catalog-aware
adapter는 opaque ref를 operator catalog에서 해석합니다.

`ModelCapability`은 reasoning, context window, token counting, input/output
`ModelModality`, tools, structured output 지원 여부를 표현합니다. 기본값은 text input과
text output만 지원하고 나머지 optional capability는 꺼진 상태입니다. Logical route
구성과 protocol별 wire shape는 [LLM 모델 라우팅](../../guides/llm-routing.md)을
확인하세요.

## Typed structured output

`AgentExecutionSpec.output_type`은 Pydantic `BaseModel`, 표준 dataclass, `TypedDict` class를
지원합니다. Declaration 단계에서 portable closed JSON Schema를 만들 수 없는 class,
external/recursive reference, unsupported keyword, non-finite JSON은 `AgentDefinitionError`로
거부됩니다. 내부 schema builder는 공개 API가 아니며 사용자는 `output_type`만 선언합니다.

Runner는 selected model의 `supports_structured_output`을 provider 호출 전에 확인합니다.
Final structured payload는 strict type/no-extra/no-coercion으로 materialize되며 text JSON
fallback은 없습니다. `run()`은 typed object를, `run_events()`는 JSON-safe `output`과
`output_type` metadata를 반환합니다. AG-UI는 JSON result, A2A는 output type 이름의 final
data artifact로 투영합니다.

| terminal code | 의미 |
| --- | --- |
| `agent_structured_output_unsupported` | 선택 model capability가 structured output을 지원하지 않음 |
| `agent_structured_output_missing` | Tool call 없는 final step에 structured payload가 없음 |
| `agent_structured_output_ambiguous` | Payload가 여러 개이거나 한 step에 tool batch와 함께 존재 |
| `agent_structured_output_invalid` | Type/schema/extra/missing/serialization shape 검증 실패 |

`output_type=None`이면 기존 `AgentRunResult`가 유지됩니다. Event metadata에는 `output`을
추가하지 않으므로 AG-UI result는 `None`, A2A final output artifact는 없음이 정본입니다.

## Static/dynamic typed context

`RunAgentInput.context`는 `AgentContext(packs, manifest, digest)` static envelope입니다.
`ContextPack`은 ID/content/source/role, sensitivity, freshness/relevance와
`ContextTokenBudget`을 가집니다. Runner는 pack을 `ModelRequest.context`에 넣고 raw prompt
concatenation 대신 `ModelRequest.assemble_messages()` 경계에서 guarded evidence message로
조립합니다.

Dynamic context는 constructor-injected `IAgentContextProvider` 하나가
`provide(run_input, model_step)` async port로 제공합니다. `refresh_context_each_step=False`는
한 invocation에서 첫 결과를 cache하고, `True`는 1-based model step마다 다시 호출합니다.
Fresh resume은 raw provider context cache를 checkpoint하지 않고 provider를 다시 호출합니다.

Durable checkpoint는 raw static context 대신 prepared static context fingerprint만 저장합니다.
Static context를 사용하던 run의 resume caller는 동일 `RunAgentInput.context`를 다시 제공해야
하며 model-bound prepared fingerprint가 다른 missing/different/additive context는
`agent_checkpoint_invalid`로 pending replay 전에 거부됩니다. Dynamic provider context는
resume에서 다시 취득합니다.

Static/dynamic pack ID는 전체에서 unique해야 합니다. Manifest는 모든 pack을 같은
순서·ID/source/role로 정확히 덮고 digest는 manifest와 전체 pack ID 순서를 덮어야 합니다.
Dynamic provider return 또는 model-step combination의 partial digest/incomplete/conflicting
provenance는 provider request 전에 `agent_model_execution_failed`; provider deadline 초과는
`agent_timeout`입니다.
Runner는 digest linkage/coverage만 검증하며 declared digest value를 content에서 재계산하지
않습니다.

Model-safe preparation은 REDACTED content, sensitive-field guard, deterministic token-budget
truncation을 적용하고 arbitrary metadata/descriptors 및 digest summary를 제거합니다. 유일한
예외는 exact key/type allowlist를 통과한 framework `retrieval` block이며 unknown key나
malformed value가 있으면 block 전체를 제거합니다. Durable context evidence도 raw content를
저장하지 않고 pack/provenance/budget/digest와 검증된 retrieval reference만 남깁니다.
Evidence의 combined context fingerprint는 같은 model step의 동일 context를 deduplicate하고
변경된 context를 별개로 구분합니다.

## RAG retrieval contracts

RAG는 `IRetriever` 결과를 model 호출 전에 `RetrievalContext`로 넣는 경로이고, agentic
RAG는 같은 port를 `RetrievalTool`로 model-callable tool에 넣는 경로입니다. 기본
retrieval API는 `IRetriever`, `RetrievalHit`, `RetrievalContext`, `RetrievalTool`입니다.

`RetrievalContext`는 `limit=5`, `max_context_tokens=2048`, `allow_empty=False`가 기본입니다.
`RunAgentInput.instruction`을 query로 사용하고 ordered hit를 JSON source frame이 앞선
budgeted evidence pack과 manifest로 변환합니다. 빈 결과는 direct 경계에서
`AgentRetrievalError`, runner에서는 provider request 전 `agent_model_execution_failed`입니다.
`allow_empty=True`만 empty context로 계속 진행합니다.

`RetrievalTool`은 `name="search"`, `limit=5`가 기본인 injected `IAgentToolProvider`입니다.
Model-facing schema에는 `query` 하나만 있고 tenant/namespace/filter는 adapter 생성 시
고정됩니다. Result는 ordinary `TOOL` history로 다음 model step에 들어가며 tool 실행의
typed failure는 `agent_tool_execution_failed`입니다. 이 경로의 raw hit content는 normal tool
history/evidence/checkpoint 의미를 따르며 classic context budget/redaction을 자동 적용하지
않습니다. 두 adapter 모두 arbitrary `RetrievalHit.metadata`를 model/evidence result에
복사하지 않습니다.

Runner는 일반 `IAgentToolProvider`도 provider instance에 method를 bind해 per-run catalog에
합치고 shared `@Agent` catalog는 mutate하지 않습니다. Wrong owner, already-bound callable,
duplicate schema name은 model request 전에 `AgentDefinitionError`입니다.

Unscoped adapter는 unscoped hit만 허용하고, tenant/namespace를 명시하면 반환 hit도 exact
scope여야 합니다. JSON이 아닌 filter, duplicate ID, blank framing field, non-finite score,
malformed span과 wrong result type은 `AgentRetrievalError`로 fail closed합니다.

Vector 확장은 `ITextEmbedding` + `IVectorSearch` + `VectorRetriever`, optional
`IReranker` + `RerankedRetriever`의 replaceable port 조합입니다. Core에는 vector backend,
in-memory fallback, index write API가 없습니다. 사용 흐름은
[Agent RAG](../../guides/agent-rag.md), embedding route는
[AI Agent 심화](../../guides/agents-advanced.md#retrieval-extension-ports)를 확인하세요.

## Memory, evaluation, cost와 telemetry

`ITaskStore`는 `USER`/`ASSISTANT` conversation transcript 전용입니다. Long-term memory는
별도 `IMemoryStore`의 `save()`, `search()`, `delete()`와 immutable `MemoryEntry` revision을
사용합니다. `MemoryRetriever`는 tenant/user/namespace와 `MemoryKind` tuple을 bind한
`IRetriever`이며 expired entry, superseded revision과 store가 delete한 entry를 hit에서
제외합니다. Duplicate/cross-scope/conflicting correction과 active correction cycle은
`AgentMemoryError`입니다. Core에는 production memory backend가 없습니다.

Offline evaluation은 `AgentEvaluationDataset(cases=tuple)`, case마다 정확히 하나인
`AgentEvaluationSample` tuple, `AgentEvaluationSuite(evaluators=tuple)`을 명시적으로
조합합니다. Built-in evaluator는 ordered tool trace, strict structured output, exact reference
precision/recall, retrieval reference groundedness를 계산합니다. `ModelJudgeEvaluator`는
injected `IModelJudge`만 사용하며 default judge가 없습니다. Report의 evidence candidate는
metric/correlation만 가진 `AgentEvidenceKind.EVALUATION`이고 repository에 자동 append되지
않습니다. `AgentEvidenceKind.SIGNAL`은 runner가 소비한 non-terminal inbound signal audit
전용입니다. Case/sample의 structured JSON과 tool arguments/metadata는 construction 시 deep
snapshot됩니다.

`ModelPricingCatalog`는 opaque logical model ref별 `ModelPrice`를 보존하는 immutable
versioned snapshot입니다. Per-million rate와 cost는 `Decimal`이며 optional cached/generic
write rate는 input rate, TTL-specific write rate는 generic write rate로 fallback합니다.
Pricing이 주입되면 `max_cost` 유무와 관계없이 매 terminal model step을 계산합니다. Routed
ref/price/input-output usage가 없거나 total/TTL cache usage가
inconsistent하거나 distinct TTL rate에 write category가 없으면 `agent_cost_unavailable`,
cumulative amount가 limit보다 크면
`agent_max_cost_exceeded`입니다. Checkpoint는 pricing fingerprint와 cumulative cost를 묶어
changed pricing resume을 `agent_checkpoint_invalid`로 거부합니다. Resume은 completed step의
`MODEL` evidence route/full usage로 cost를 재계산해 exact step coverage와 checkpoint total을
대조합니다. Built-in price는 없습니다.

`ModelUsage`는 `cached_input_tokens`, total `cache_write_input_tokens`, TTL별
`cache_write_5m_input_tokens`/`cache_write_1h_input_tokens`도 표현합니다.
`AgentSpanRecord`는 `RUN`, `MODEL`, `TOOL`, `RETRIEVAL`의 completed nanosecond interval과
scalar metadata만 `IAgentTelemetry.record()`에 전달합니다. Prompt/context/completion,
retrieval query/content, tool arguments/results는 core record에 넣지 않습니다. Sink failure는
`AgentTelemetryError`입니다. 전체 사용법과 실패 경계는
[Agent Memory, Evaluation, Cost와 Telemetry](../../guides/agent-operations.md)를 확인하세요.

## Public API

::: spakky.agent
    options:
      show_root_heading: false

## 실행

::: spakky.agent.execution
    options:
      show_root_heading: false

::: spakky.agent.inbound
    options:
      show_root_heading: false

::: spakky.agent.runner
    options:
      show_root_heading: false

::: spakky.agent.runner_factory
    options:
      show_root_heading: false

## Event

::: spakky.agent.event
    options:
      show_root_heading: false

## Dispatcher

::: spakky.agent.dispatcher
    options:
      show_root_heading: false

## State

::: spakky.agent.state
    options:
      show_root_heading: false

## Signal

::: spakky.agent.signal
    options:
      show_root_heading: false

::: spakky.agent.signal_consumption
    options:
      show_root_heading: false

## Evidence

::: spakky.agent.evidence
    options:
      show_root_heading: false

## Context

::: spakky.agent.context
    options:
      show_root_heading: false

## Retrieval

::: spakky.agent.retrieval
    options:
      show_root_heading: false

## Memory

::: spakky.agent.memory
    options:
      show_root_heading: false

## Evaluation

::: spakky.agent.evaluation
    options:
      show_root_heading: false

## Cost

::: spakky.agent.cost
    options:
      show_root_heading: false

## Telemetry

::: spakky.agent.telemetry
    options:
      show_root_heading: false

## Compaction

::: spakky.agent.compaction
    options:
      show_root_heading: false

## Recovery

::: spakky.agent.recovery
    options:
      show_root_heading: false

## Approval

::: spakky.agent.approval
    options:
      show_root_heading: false

## Cancellation

::: spakky.agent.cancellation
    options:
      show_root_heading: false

## Delegation

::: spakky.agent.delegation
    options:
      show_root_heading: false

## Safety

::: spakky.agent.safety
    options:
      show_root_heading: false

## Tooling

::: spakky.agent.tooling
    options:
      show_root_heading: false

## Signal Hooks

::: spakky.agent.hooks
    options:
      show_root_heading: false

## Yield

::: spakky.agent.yield_
    options:
      show_root_heading: false

## Model Interface

::: spakky.agent.interfaces
    options:
      show_root_heading: false

::: spakky.agent.interfaces.model
    options:
      show_root_heading: false

::: spakky.agent.interfaces.repository
    options:
      show_root_heading: false

::: spakky.agent.interfaces.task_store
    options:
      show_root_heading: false

## Types

::: spakky.agent.types
    options:
      show_root_heading: false

## Plugin

::: spakky.agent.main
    options:
      show_root_heading: false

::: spakky.agent.post_processor
    options:
      show_root_heading: false

## 에러

::: spakky.agent.error
    options:
      show_root_heading: false
