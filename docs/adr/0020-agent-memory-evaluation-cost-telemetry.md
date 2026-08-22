---
title: "ADR-0020: Semantic memory, evaluation, pricing과 Agent telemetry"
date: '2026-08-23'
status: accepted
---

# ADR-0020: Semantic memory, evaluation, pricing과 Agent telemetry

> Conversation transcript와 long-term semantic memory를 분리하고 evaluation을 explicit offline contract로 둡니다.
> Model price는 operator-owned immutable mapping에서 exact cost로 계산하고 Agent telemetry는 scalar metadata만 OTel로 옮기며 prompt/context/tool body를 수집하지 않습니다.

## 맥락 (Context)

`ITaskStore`는 ADR-0013에서 `conversation_id`별 user/assistant turn을 재생하는 server-side transcript port로 도입됐습니다. 이를 long-term memory store로 확장하면 conversation replay와 tenant/user-scoped knowledge의 TTL, correction, delete 의미가 하나의 API에 섞입니다. 특히 transcript append와 immutable memory revision은 서로 다른 수명주기를 갖습니다.

Agent quality도 runtime loop의 숨은 model call로 판정하면 재현성과 비용 authority를 잃습니다. Deterministic tool trace, strict typed output, reference precision/recall과 retrieval groundedness는 explicit case/sample만으로 계산할 수 있고, model judge가 필요한 경우도 어느 model을 쓸지 application이 선택해야 합니다.

Provider usage는 수집되었지만 price를 provider/model name에서 추론하면 시점·계약·통화별 요금을 안전하게 보존할 수 없습니다. 비용 limit을 실행하려면 opaque logical model ref에 결속된 operator price, cache token을 포함한 usage, durable resume에서 재해석되지 않는 pricing identity가 필요합니다.

Observability에 raw prompt, context, retrieval query/body, tool arguments/results를 싣으면 운영 편의는 얻지만 data exposure boundary가 확장됩니다. Core는 backend-neutral해야 하고 OpenTelemetry plugin만 OTel parent/status/span-kind/semantic attribute를 알아야 합니다.

## 결정 (Decision)

### 1. Conversation history와 long-term memory를 서로 다른 port로 유지합니다

`ITaskStore`/`ConversationTurn`은 기존대로 `conversation_id`별 user/assistant transcript append/load만 소유합니다. System/evidence framing, TTL, memory correction, delete를 이 port에 추가하지 않습니다.

Long-term memory는 다음 contract로 분리합니다.

| Contract | 의미 |
|----------|------|
| `MemoryKind` | `SEMANTIC`, `EPISODIC`, `USER` |
| `MemoryEntry` | exact scope의 frozen content revision + provenance + TTL + optional correction link |
| `IMemoryStore` | immutable revision `save`, scoped `search`, explicit scoped `delete` |
| `MemoryRetriever` | exact user binding을 보존하는 `IRetriever` adapter |

`MemoryEntry`는 id/kind/content/source/revision/content digest, tenant/user/namespace, timezone-aware created time, optional later expiry, optional `supersedes`를 갖습니다. Frozen entry를 update하지 않고 정정은 새 revision이 이전 id를 supersede하는 방식으로 표현합니다. Self-supersede, naive timestamp, expiry ≤ created는 definition error입니다.

`MemoryRetriever` constructor는 `IMemoryStore`, nonblank tenant/user/namespace와 nonempty unique kind tuple을 bind합니다. `IRetriever.retrieve()`의 tenant/namespace가 binding과 exact match해야 하고 store result의 tenant/user/namespace/kind도 다시 검증합니다. Expired entry와 active correction이 supersede한 target은 hit가 되지 않고, 같은 target의 active correction이 복수거나 active correction graph에 cycle이 있으면 `AgentMemoryError`입니다. Explicit delete된 entry를 search에서 제외하는 것은 store 구현의 계약입니다.

Memory contract는 `spakky-agent`에 두고 별도 memory package/plugin을 만들지 않습니다. Core는 production `IMemoryStore`나 auto in-memory fallback을 제공하지 않으며 application/vendor가 persistence와 삭제 정책을 명시적으로 선택해야 합니다.

### 2. Evaluation은 explicit sample만 소비하는 pure offline API입니다

`AgentEvaluationDataset`/`AgentEvaluationCase`는 expected tool calls, optional output type/expected JSON, expected citation refs를 갖습니다. `AgentEvaluationSample`은 이미 관찰된 structured output, tool calls, citation refs, retrieval refs를 case ref에 결속합니다. Case/sample construction은 nested JSON과 tool arguments/metadata를 recursive immutable snapshot으로 고정합니다. Suite는 sample이 dataset case를 exactly once 커버하는지 확인하고 **dataset case order × evaluator order**로 sequential evaluation합니다. Runner를 호출하거나 sample을 자동 생성하지 않습니다.

Built-in deterministic evaluator는 다음입니다.

- `ToolTraceEvaluator`: call id/metadata를 제외한 exact ordered name + JSON arguments
- `StructuredOutputEvaluator`: Wave 3 strict output materializer와 optional expected JSON
- `CitationEvaluator`: exact reference set의 precision와 recall
- `RetrievalGroundednessEvaluator`: cited ref가 retrieved ref에 있는 비율; raw retrieval content는 읽지 않음

`ModelJudgeEvaluator`는 `IModelJudge`를 required constructor argument로 받고 explicit metric/name/threshold를 적용합니다. Core는 default judge model, provider, network path를 선택하지 않습니다.

Result score와 threshold는 finite `0..1`이고 report score는 explicit results의 unweighted mean이며 report pass는 전체 metric conjunction입니다. `evidence_candidates()`는 raw prompt/context/output 없이 evaluator, metric, pass, score, case/sample ref만 `AgentEvidenceKind.EVALUATION`으로 만듭니다. Caller가 선택해 repository에 append할 수 있지만 suite가 runtime evidence를 자동 변경하지 않습니다. User/steering signal audit은 별도 `AgentEvidenceKind.SIGNAL`이고 `EVALUATION`을 사용하지 않습니다.

### 3. Price는 operator mapping, cost는 exact runner accounting입니다

`ModelPrice`는 per-million input/output `Decimal` rate와 optional cached-input/aggregate-write/5m-write/1h-write rate를 갖습니다. 모든 rate는 finite nonnegative이고 5m/1h는 aggregate write, aggregate write는 input rate로 fallback합니다. `ModelPricingCatalog`은 version, currency(default `USD`), opaque logical model-ref mapping과 operator metadata를 defensive copy + read-only mapping으로 snapshot합니다. Fingerprint는 version/currency/sorted rates/sorted metadata를 모두 SHA-256로 결속합니다.

`ModelUsage` input/output token은 pricing에 필수이고 cached + aggregate write는 inclusive input을 넘지 못합니다. 5m/1h category가 하나라도 있으면 합이 aggregate write와 exact match해야 하며, distinct TTL rate가 설정된 nonzero write에 category가 없으면 fail closed합니다. `ModelCost`는 exact amount, currency, pricing version, model ref와 inclusive input/output/cached/aggregate-write/5m-write/1h-write token을 보존합니다. Provider나 core에 built-in price 상수는 없으며 unknown model/price/usage를 default price로 fallback하지 않습니다.

`AgentRunner`/`AgentRunnerFactory`는 optional pricing을 주입받습니다. Pricing이 있으면 `max_cost`가 없어도 every terminal model step을 route `model_ref` + usage로 계산하고 missing price/usage는 `agent_cost_unavailable`입니다. `max_cost` 자체가 있는데 pricing이 없으면 첫 request 전 같은 code로 실패합니다. Response 이후 cumulative cost가 limit보다 크면 `agent_max_cost_exceeded`이며 tool dispatch·next model·success final을 막습니다.

Step metadata는 amount/currency/pricing version/model ref를, final/event metadata는 cumulative total/currency/version을 JSON-safe decimal 문자열로 남깁니다. Durable checkpoint는 cumulative cost와 pricing fingerprint/version/currency를 보존하지만 resume는 이 값만 신뢰하지 않습니다. Exact catalog fingerprint/version/currency를 확인한 뒤 append-only MODEL evidence의 step별 route/usage로 전체 cost를 재계산하고 checkpoint total과 대조합니다. Missing/duplicate/invalid evidence, partial/malformed pricing field, recomputed total mismatch는 `agent_checkpoint_invalid`로 fail closed해 이미 계산된 step을 새 price로 재해석/중복 청구하지 않습니다.

OpenAI, Anthropic, Google adapter는 native cache usage를 core cache fields로 정규화합니다. OpenAI는 prompt cached/aggregate-write details, Anthropic은 cache read/creation을 inclusive input에 합산하고 SDK `cache_creation` 5m/1h category를 보존합니다. Anthropic nonzero aggregate creation에 breakdown이 없거나 category 합이 aggregate와 다르면 `LlmResponseError`입니다. Google은 cached content만 제공합니다.

### 4. Core telemetry는 body-free completed record만 제공합니다

`AgentSpanRecord`는 RUN/MODEL/TOOL/RETRIEVAL kind, name, `time_ns()` start/end, OK/ERROR status + optional exact error code, immutable scalar attributes를 갖습니다. Attribute key는 nonblank이고 value는 `str|bool|int|finite float`만 허용합니다. Runner는 run/conversation identity/outcome, model route/usage/cost, tool name/identity/kind, classic retrieval hit-count/limit/bound scope만 기록합니다. Prompt, system instruction, model input/output body, context/retrieval query·body, tool arguments/results는 attribute로 만들지 않습니다.

`IAgentTelemetry.record()`는 completed record를 동기적으로 받는 optional outbound port입니다. `RetrievalContext`는 RETRIEVAL record를 내지만 agentic `RetrievalTool`은 TOOL record의 `agent.tool.kind="retrieval"`로 표현합니다. Sink exception은 silent drop하지 않고 `AgentTelemetryError`로 fail closed합니다. Core는 OTel SDK를 import하지 않습니다.

Public `run()`과 neutral `run_events()`는 completed, failed, approval-paused, cancelled RUN outcome의 accumulated cost attributes를 동일하게 남깁니다. Cost-limit failure와 pause에서도 실제로 이미 사용한 total/currency/pricing version을 숨기지 않습니다.

### 5. `spakky-opentelemetry`만 OTel semantic mapping을 소유합니다

Plugin은 `OpenTelemetryAgentTelemetry`를 등록하고 `IAgentTelemetry`에 bind합니다. Spakky production dependency는 `spakky`, `spakky-tracing`, `spakky-agent`이며 `spakky-llm`에 의존하지 않습니다. `spakky-logging`은 optional extra입니다.

| Agent kind | OTel operation | OTel span kind |
|------------|----------------|----------------|
| `RUN` | `invoke_agent` | `INTERNAL` |
| `MODEL` | `generate_content` | `CLIENT` |
| `TOOL` | `execute_tool` | `INTERNAL` |
| `RETRIEVAL` | `retrieval` | `CLIENT` |

Adapter는 `AgentSpanRecord` nanosecond를 `Tracer.start_span(start_time=...)`/`Span.end(end_time=...)`에 exact 전달합니다. `TraceContext.get()`이 있으면 same trace/span id·flags의 non-recording parent, 없으면 explicit empty context로 root span을 만듭니다. Ambient current OTel span을 자동 상속하거나 Agent records 사이의 계층을 추론하지 않습니다.

OK는 `StatusCode.OK`, ERROR는 error-code description의 `StatusCode.ERROR`와 `error.type`으로 매핑합니다. `gen_ai.operation.name`과 `error.type`은 caller override를 무시하고 adapter가 고정합니다. Core scalar validation을 다시 확인하고 prompt/system messages/context/retrieval query·body/tool argument·result의 raw-body key를 case-insensitive denylist로 제거한 뒤 span을 종료합니다.

이 경계는 OpenTelemetry Python의 explicit `context`, `kind`, `attributes`, `start_time`을 받는 `Tracer.start_span()`과 `Span.end(end_time)` API를 사용합니다. OTel mapping은 core에 역참조되지 않습니다.

## 대안 (Alternatives)

### 대안 A: `ITaskStore`에 semantic memory를 추가합니다

Store 포트가 하나라서 간단해 보이지만 conversation id별 ordered transcript와 tenant/user/namespace별 TTL·correction·delete revision의 수명주기가 섞입니다. `ITaskStore`를 transcript로 유지하고 `IMemoryStore`를 분리합니다.

### 대안 B: Core가 in-memory memory store를 자동 제공합니다

Demo는 쉬워지지만 process lifetime, tenant isolation, delete durability를 production contract로 오해할 수 있습니다. Test fake와 production fallback을 분리하고 application/vendor가 `IMemoryStore`를 명시합니다.

### 대안 C: Evaluator가 숨은 default model judge를 선택합니다

Evaluation이 network, credential, route, 비용을 숨기고 deterministic offline suite와 다른 authority를 갖게 됩니다. Built-in은 pure evaluator로 유지하고 model judge는 required `IModelJudge`로만 추가합니다.

### 대안 D: Provider adapter에 요금 상수를 내장합니다

Model/provider price는 빠르게 바뀌고 계약·region·통화에 따라 다릅니다. SDK adapter는 usage만 정규화하고 operator가 versioned `ModelPricingCatalog`를 제공합니다.

### 대안 E: Trace에 prompt/context/tool body를 저장합니다

Debug 편의는 있지만 Agent input과 tool result의 secret/PII 영속 범위를 관찰 backend까지 확장합니다. Core record를 scalar-only/body-free로 제한하고 OTel adapter도 denylist로 재검증합니다.

## 결과 (Consequences)

### 긍정적

- Transcript replay와 long-term memory가 각자의 scope·lifecycle를 유지합니다.
- Memory correction과 TTL이 immutable revision/provenance에 결속됩니다.
- Offline quality metric과 optional model judge authority가 명시적으로 분리됩니다.
- Operator price와 provider usage로 exact cumulative cost/limit/resume 의미를 재현할 수 있습니다.
- Core telemetry에 raw Agent body가 들어가지 않고 OTel mapping이 plugin에 한정됩니다.

### 부정적

- Application은 production `IMemoryStore`를 직접 제공해야 합니다.
- Pricing을 opt in하면 missing provider usage/price를 무시하고 계속할 수 없습니다.
- `max_cost`는 response 이후 집행되므로 limit을 넘긴 response의 원격 비용은 이미 발생했을 수 있습니다.
- Scalar-only telemetry는 raw prompt/body를 이용한 observability query를 제공하지 않습니다.
- Telemetry sink failure는 silent loss 대신 `AgentTelemetryError`로 execution을 fail closed할 수 있습니다.

### 중립적

- Evaluation report의 evidence candidate를 영속할지는 offline caller가 결정합니다.
- `MemoryRetriever`는 existing `RetrievalContext`/`RetrievalTool`에 주입할 수 있지만 memory store와 conversation store를 합치지 않습니다.
- `spakky-opentelemetry` Agent spans은 ambient `TraceContext`의 child이지만 completed record 사이의 hierarchy를 자동 생성하지 않습니다.
- ADR-0017의 loop/authority/limit timing/checkpoint 결정은 유지하되 public limit field 목록에 `max_cost`를 추가하는 부분만 이 ADR이 amend합니다. ADR-0018의 context/privacy와 ADR-0019의 retrieval scope/provenance는 유지됩니다.

## 참고 자료

- [ADR-0017: Bounded iterative model/tool loop](0017-bounded-iterative-agent-loop.md)
- [ADR-0018: Typed agent output과 composed execution context](0018-typed-agent-output-and-context.md)
- [ADR-0019: Minimal retrieval runtime](0019-minimal-retrieval-runtime.md)
- [OpenTelemetry Python `Tracer.start_span`](https://opentelemetry-python.readthedocs.io/en/stable/_modules/opentelemetry/trace.html)
- [OpenTelemetry Python `Span.end`](https://opentelemetry-python.readthedocs.io/en/stable/_modules/opentelemetry/trace/span.html)
- [OpenTelemetry Python status](https://opentelemetry-python.readthedocs.io/en/stable/_modules/opentelemetry/trace/status.html)
