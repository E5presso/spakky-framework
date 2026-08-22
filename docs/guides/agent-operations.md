# Agent Memory, Evaluation, Cost와 Telemetry

> Long-term memory는 scoped `IMemoryStore`를 retrieval에 연결하고, evaluation은 명시적인 offline sample을 채점합니다. Cost와 telemetry는 operator가 주입할 때만 runner에 적용되는 운영 경계입니다.

네 기능은 서로 대신하지 않습니다.

| 목적 | 시작 API | 기본 동작 |
| --- | --- | --- |
| 사용자별 장기 기억 | `MemoryRetriever` | backend와 scope를 명시해야 함 |
| 회귀 평가 | `AgentEvaluationSuite` | dataset/sample/evaluator를 모두 명시해야 함 |
| 비용 집행 | `ModelPricingCatalog` | built-in price 없음 |
| 실행 관측 | `IAgentTelemetry` | adapter를 주입하지 않으면 span 없음 |

`ITaskStore`는 이 표의 memory store가 아닙니다. `ITaskStore`는 같은 conversation의
`USER`/`ASSISTANT` transcript를 다음 run에 재생할 뿐이고, 장기 기억의 TTL, correction,
tenant/user scope와 delete는 `IMemoryStore`가 소유합니다.

## Long-term memory를 기존 RAG에 연결하기

애플리케이션은 `IMemoryStore`를 구현하고 `MemoryRetriever`에 tenant, user, namespace를
한 번 bind합니다. 그 retriever를 기존 `RetrievalContext` 또는 `RetrievalTool`로 감싸면
classic RAG와 agentic RAG가 같은 memory backend를 공유합니다.

아래 store는 예제를 실행하기 위한 local fake이며 framework의 production fallback이
아닙니다. 제품에서는 같은 세 메서드를 기존 database나 vendor memory 경계에 연결하세요.

```python
import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import override

from spakky.agent import (
    IMemoryStore,
    JsonObject,
    MemoryEntry,
    MemoryKind,
    MemoryRetriever,
    RetrievalContext,
    RetrievalTool,
    RunAgentInput,
)


class DemoMemoryStore(IMemoryStore):
    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._deleted: set[str] = set()

    @override
    async def save(self, entry: MemoryEntry) -> None:
        self._entries[entry.id] = entry

    @override
    async def search(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str,
        user_id: str,
        namespace: str,
        kinds: tuple[MemoryKind, ...],
        filters: JsonObject,
    ) -> Sequence[MemoryEntry]:
        _ = filters
        needle = query.casefold()
        return tuple(
            entry
            for entry in self._entries.values()
            if entry.id not in self._deleted
            and entry.tenant_id == tenant_id
            and entry.user_id == user_id
            and entry.namespace == namespace
            and entry.kind in kinds
            and needle in entry.content.casefold()
        )[:limit]

    @override
    async def delete(
        self,
        entry_id: str,
        *,
        tenant_id: str,
        user_id: str,
        namespace: str,
    ) -> None:
        entry = self._entries.get(entry_id)
        if entry is not None and (
            entry.tenant_id,
            entry.user_id,
            entry.namespace,
        ) == (tenant_id, user_id, namespace):
            self._deleted.add(entry_id)


async def memory_demo() -> None:
    now = datetime.now(UTC)
    store = DemoMemoryStore()
    await store.save(
        MemoryEntry(
            id="memory-1",
            kind=MemoryKind.USER,
            content="알림 채널은 SMS입니다.",
            source="profile:notification",
            revision="r1",
            content_digest="sha256:memory-1",
            tenant_id="tenant-42",
            user_id="user-7",
            namespace="support",
            created_at=now,
        )
    )
    await store.save(
        MemoryEntry(
            id="memory-2",
            kind=MemoryKind.USER,
            content="알림 채널은 이메일입니다.",
            source="profile:notification",
            revision="r2",
            content_digest="sha256:memory-2",
            tenant_id="tenant-42",
            user_id="user-7",
            namespace="support",
            created_at=now,
            expires_at=now + timedelta(days=365),
            supersedes="memory-1",
        )
    )

    memory = MemoryRetriever(
        store,
        tenant_id="tenant-42",
        user_id="user-7",
        namespace="support",
    )
    classic = RetrievalContext(
        memory,
        tenant_id="tenant-42",
        namespace="support",
        filters={},
    )
    agentic = RetrievalTool(
        memory,
        name="memory_search",
        tenant_id="tenant-42",
        namespace="support",
        filters={},
    )

    context = await classic.provide(
        RunAgentInput(
            state_id="memory-demo",
            instruction="알림 채널",
        ),
        1,
    )
    assert context.packs[0].id == "retrieval:memory-2"
    assert agentic.tool_catalog.descriptors[0].schema.name == "memory_search"


asyncio.run(memory_demo())
```

`MemoryEntry`는 immutable revision입니다. 기존 값을 고칠 때 같은 ID를 덮어쓰는 대신 새
entry의 `supersedes`에 이전 ID를 기록합니다. `MemoryRetriever`는 expired revision,
superseded target, store가 delete한 entry를 hit에서 제외합니다. `MemoryKind`는
`SEMANTIC`, `EPISODIC`, `USER`이며 retriever 생성 시 허용 tuple을 줄이지 않으면 세 종류를
모두 요청합니다.

Scope는 양방향 exact match입니다. `MemoryRetriever`에 bind한 tenant/namespace와
`RetrievalContext` 또는 `RetrievalTool`의 tenant/namespace가 같아야 하고, store가 반환한
entry는 tenant, user, namespace가 모두 같아야 합니다. Cross-user result, duplicate ID,
충돌하거나 cycle을 이루는 correction, malformed filter는 `AgentMemoryError`로 fail
closed합니다.

`MemoryRetriever`는 memory-specific 값을 arbitrary `RetrievalHit.metadata`에만 두므로 기존
retrieval privacy 규칙에 따라 model context와 tool result에는 복사되지 않습니다. Model이
보는 값은 active revision의 content와 표준 retrieval provenance입니다. Framework에는
production memory backend, 자동 write, 암묵적 delete가 없습니다.

## Explicit sample을 offline 평가하기

Evaluation은 live Agent를 대신 실행하지 않습니다. 이미 관측한 structured output, tool
trace와 reference tuple을 `AgentEvaluationSample`로 만들고 dataset의 case를 정확히 한
sample씩 덮어야 합니다. Dataset order와 evaluator tuple order가 report order입니다.
Case expected output/tool arguments와 sample structured output/tool arguments는 construction
시 deep snapshot되므로 caller가 원본 nested dict/list를 바꿔도 평가 입력은 변하지 않습니다.

```python
import asyncio

from pydantic import BaseModel

from spakky.agent import (
    AgentEvaluationCase,
    AgentEvaluationDataset,
    AgentEvaluationSample,
    AgentEvaluationSuite,
    CitationEvaluator,
    ModelToolCall,
    RetrievalGroundednessEvaluator,
    StructuredOutputEvaluator,
    ToolTraceEvaluator,
)


class SupportAnswer(BaseModel):
    answer: str


async def evaluation_demo() -> None:
    case = AgentEvaluationCase(
        id="notification-channel",
        expected_tool_calls=(
            ModelToolCall(
                name="memory_search",
                arguments={"query": "알림 채널"},
                call_id="expected-call",
            ),
        ),
        output_type=SupportAnswer,
        expected_output={"answer": "이메일"},
        expected_citations=("memory-2",),
    )
    dataset = AgentEvaluationDataset(
        id="support-v1",
        cases=(case,),
    )
    sample = AgentEvaluationSample(
        id="sample-1",
        case_ref=case.id,
        structured_output={"answer": "이메일"},
        tool_calls=(
            ModelToolCall(
                name="memory_search",
                arguments={"query": "알림 채널"},
                call_id="actual-call",
            ),
        ),
        citations=("memory-2",),
        retrieval_refs=("memory-2",),
    )
    suite = AgentEvaluationSuite(
        evaluators=(
            ToolTraceEvaluator(),
            StructuredOutputEvaluator(),
            CitationEvaluator(),
            RetrievalGroundednessEvaluator(),
        )
    )

    report = await suite.evaluate(dataset, (sample,))
    assert report.passed is True
    assert report.score == 1.0


asyncio.run(evaluation_demo())
```

Built-in evaluator의 의미는 좁고 결정적입니다.

| Evaluator | 채점 대상 | 중요한 경계 |
| --- | --- | --- |
| `ToolTraceEvaluator` | ordered tool name과 arguments | call ID는 무시 |
| `StructuredOutputEvaluator` | strict typed output | text JSON fallback 없음 |
| `CitationEvaluator` | exact reference precision/recall | 두 metric을 따로 반환 |
| `RetrievalGroundednessEvaluator` | cited ref 중 retrieved ref 비율 | raw content를 읽지 않음 |

Custom metric은 stable `name` property와
`async evaluate(case, sample) -> Sequence[AgentEvaluationResult]`를 가진
`IAgentEvaluator`로 추가합니다. Suite는 evaluator/case/sample correlation과 같은 pair 안의
metric uniqueness를 다시 검증합니다. Report의 `passed`는 모든 metric의 AND이고 `score`는
명시된 metric score의 unweighted mean입니다.

`ModelJudgeEvaluator`는 application이 구현한 `IModelJudge.judge(case, sample)`를 감싸는
optional adapter입니다. Score는 `0.0`부터 `1.0` 사이여야 하며 built-in judge나 model
fallback은 없습니다.

`AgentEvaluationReport.evidence_candidates()`는 metric, pass, score, case/sample ref만 가진
`AgentEvidenceKind.EVALUATION` candidate를 만듭니다. Repository append는 caller가
결정하며 raw output, prompt, context를 자동 저장하지 않습니다. 반면
`AgentEvidenceKind.SIGNAL`은 runner가 실제로 소비한 non-terminal inbound signal의 ID와
payload를 남기는 runtime audit입니다. Evaluation evidence와 signal audit을 서로 대신해
사용하지 마세요.

## Logical model ref에 가격을 붙이기

가격은 provider나 physical model 문자열에서 추론하지 않습니다. Operator가 사용하는
logical model ref와 같은 key로 immutable, versioned `ModelPricingCatalog`를 만들고
`Decimal` per-million-token rate를 명시합니다.

```python
from decimal import Decimal
from typing import override

from spakky.agent import (
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentRunnerFactory,
    AgentSpanRecord,
    IAgentTelemetry,
    ModelPrice,
    ModelPricingCatalog,
)


class SpanCollector(IAgentTelemetry):
    def __init__(self) -> None:
        self.records: list[AgentSpanRecord] = []

    @override
    def record(self, span: AgentSpanRecord) -> None:
        self.records.append(span)


pricing = ModelPricingCatalog(
    version="pricing-2026-08-23",
    prices={
        "support/primary": ModelPrice(
            input_per_million=Decimal("2.00"),
            output_per_million=Decimal("8.00"),
            cached_input_per_million=Decimal("0.50"),
            cache_write_input_per_million=Decimal("2.50"),
            cache_write_5m_input_per_million=Decimal("2.50"),
            cache_write_1h_input_per_million=Decimal("4.00"),
        )
    },
)
spec = AgentExecutionSpec(
    name="support_agent",
    limits=AgentExecutionLimits(
        max_steps=8,
        max_tool_calls=32,
        max_cost=Decimal("0.25"),
    ),
)
telemetry = SpanCollector()
runner_factory = AgentRunnerFactory(
    pricing=pricing,
    telemetry=telemetry,
)

assert spec.limits.max_cost == Decimal("0.25")
assert runner_factory is not None
```

애플리케이션에서는 이 `spec`을 `@Agent(spec=spec)`에 전달하고 inbound adapter는 injected
`IAgentRunnerFactory.open_runner()`로 해당 Agent의 runner를 엽니다.
`AgentRunnerFactory(pricing=...)`는 모든 factory-opened run에 같은 pricing snapshot을
적용합니다. 애플리케이션은 `ModelPricingCatalog`를 Pod factory로 제공해 DI할 수도 있고,
개별 runner에 `with_pricing()`을 사용할 수도 있습니다. Framework에는 built-in price가
없습니다.

Pricing이 주입되면 `max_cost`가 없어도 각 terminal model step의 cost를 계산합니다.
`max_cost`만 선언하고 pricing이 없으면 provider 호출 전에 `agent_cost_unavailable`입니다.
Pricing이 있는데 routed logical ref가 없거나 unknown이거나 `input_tokens`/
`output_tokens`가 없거나 cache usage가 input usage보다 크면 해당 model call 뒤
`agent_cost_unavailable`로 종료하며 tool이나 public final로 진행하지 않습니다.

Step cost를 누적한 결과가 `max_cost`보다 크면 즉시 `agent_max_cost_exceeded`입니다. 정확히
같은 값으로 final에 도달하는 것은 허용하지만 tool continuation이 다음 model request를
필요로 하면 preflight가 `total_cost >= max_cost`를 exhausted budget으로 거부합니다.
Final/event/error metadata에는 cumulative `total_cost`, currency, pricing version이 남고 step
metadata에는 해당 `ModelCost`가 남습니다.

Durable checkpoint는 cumulative cost와 pricing fingerprint/version/currency를 함께
저장합니다. Resume에는 같은 pricing fingerprint와 exact version/currency가 필요하며 다른
version/rate/metadata를 주입하면 pending action 전에 `agent_checkpoint_invalid`입니다.
Runner는 완료된 모든 model step의 `MODEL` evidence에 남은 route와 full usage로 cost를 다시
계산해 checkpoint total과 exact step coverage를 대조합니다. Evidence가 없거나 중복·변조된
경우도 fail closed하며 이미 계산된 step을 다시 청구하지 않습니다.

## Provider usage와 cache rate

`ModelUsage`는 `input_tokens`, `output_tokens`, `total_tokens`에 더해
`cached_input_tokens`, total `cache_write_input_tokens`, TTL별
`cache_write_5m_input_tokens`/`cache_write_1h_input_tokens`를 가집니다. Provider adapter는
official SDK usage를 다음처럼 매핑합니다.

| Adapter | cached input | total cache write | TTL breakdown |
| --- | --- | --- | --- |
| OpenAI-compatible | `cached_tokens` | `cache_write_tokens` | 현재 보고하지 않음 |
| Anthropic | `cache_read_input_tokens` | `cache_creation_input_tokens` | `cache_creation.ephemeral_5m_input_tokens` / `cache_creation.ephemeral_1h_input_tokens` |
| Google | `cached_content_token_count` | 현재 보고하지 않음 | 현재 보고하지 않음 |

Optional cached/generic cache-write rate를 생략하면 input rate가 사용되고, TTL-specific
rate를 생략하면 generic cache-write rate가 사용됩니다. `input_tokens`는 cache read/write를
포함한 전체 input이며 regular input은 그 두 값을 뺀 나머지입니다. TTL breakdown이
존재하면 5-minute + 1-hour 합이 total cache write와 정확히 같아야 합니다. Anthropic
adapter는 nonzero cache write에 TTL breakdown이 없거나 합이 맞지 않으면
`LlmResponseError`로 거부합니다. Pricing boundary는 distinct TTL rate가 있는데 write usage가
분류되지 않은 경우까지 `AgentPricingError`/`agent_cost_unavailable`로 fail closed합니다.
Cost 계산에는
`input_tokens`와 `output_tokens`가 필수이고 token budget을 함께 켰다면 기존 규칙대로
`total_tokens`도 필수입니다.

## Privacy-safe Agent telemetry

`IAgentTelemetry`는 completed `AgentSpanRecord`만 받는 sync outbound port입니다. Runner는
`RUN`, `MODEL`, `TOOL`, `RETRIEVAL` operation을 nanosecond timestamp와 scalar metadata로
기록합니다. Adapter가 없으면 no-op이고, adapter가 실패하면 backend exception을
`AgentTelemetryError`로 정규화해 숨기지 않습니다.

Core span에는 prompt, context, system instruction, completion, retrieval query/content,
tool arguments/result가 들어가지 않습니다. Model span은 route와 usage/cost scalar,
tool span은 name/identity/kind, classic `RetrievalContext` span은 limit/hit count와 fixed
tenant/namespace만 기록합니다. Agentic `RetrievalTool`은 별도 retrieval body span이 아니라
`TOOL` span의 `agent.tool.kind="retrieval"`로 보입니다.

Pricing이 활성화되면 `run()`과 `run_events()`의 `RUN` span은 success, typed failure,
approval pause와 canonical cancellation 모두에서 그 시점의 actual cumulative cost,
currency와 pricing version을 보존합니다. Cancellation은 두 surface 모두
`agent.run.outcome="cancelled"`이며 아직 계산되지 않은 가격을 추측해 넣지는 않습니다.

`spakky-opentelemetry`를 로드하면 `OpenTelemetryAgentTelemetry`를 자동 등록하고
`IAgentTelemetry`에 bind합니다. Injected `AgentRunnerFactory`로 연 run은 이 binding을
사용합니다. Direct runner를 조립한다면 Agent에 telemetry를 constructor-inject하거나
`with_telemetry()`를 명시합니다.

OpenTelemetry adapter는 ambient Spakky `TraceContext`가 있으면 그 exact trace/span을 parent로
사용하고, record의 nanosecond 시작/종료 시간을 그대로 전달합니다. `RUN`/`TOOL`은 OTel
`INTERNAL`, `MODEL`/`RETRIEVAL`은 `CLIENT` span이며 `gen_ai.operation.name`, OTel
OK/ERROR status와 optional `error.type`을 기록합니다. Raw-body denylist는 caller가 같은 key를
넣어도 제거합니다.

이 binding 자체가 network exporter를 새로 약속하지는 않습니다. OTLP, console, none 선택과
endpoint/sample rate는 기존 `OpenTelemetryConfig`가 소유합니다. 설치·exporter 설정과
privacy attribute 표는 [OpenTelemetry 통합](opentelemetry.md)을 확인하세요.

## 운영 체크리스트

- Conversation transcript에는 `ITaskStore`, 장기 기억에는 scoped `IMemoryStore`를 사용합니다.
- Memory store는 exact tenant/user/namespace, immutable revision, TTL와 explicit delete를 구현합니다.
- Evaluation에는 dataset case마다 sample을 정확히 하나 주고 evaluator tuple을 명시합니다.
- Model judge, prices, memory backend는 애플리케이션이 제공하며 silent fallback을 기대하지 않습니다.
- Cost budget에는 `Decimal`만 쓰고 pricing version을 배포 configuration과 함께 고정합니다.
- Telemetry attribute에는 scalar correlation만 넣고 raw model/tool/retrieval body를 보내지 않습니다.

## 함께 보기

- [Agent RAG](agent-rag.md): `IRetriever`를 classic context와 agentic tool로 여는 기본 흐름입니다.
- [AI Agent 심화](agents-advanced.md): durable checkpoint, evidence, context privacy를 확인합니다.
- [LLM 모델 라우팅](llm-routing.md): pricing key와 같은 opaque logical model ref를 구성합니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): memory/evaluation/cost/telemetry signature입니다.
- [spakky-opentelemetry API Reference](../api/plugins/spakky-opentelemetry.md): OTel bridge implementation surface입니다.
