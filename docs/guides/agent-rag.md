# Agent RAG

> RAG (Retrieval-Augmented Generation)는 model을 호출하기 전에 관련 정보를 찾아 `AgentContext`로 넣는 방식입니다. Agentic RAG는 같은 `IRetriever`를 `RetrievalTool`로 감싸 model이 필요할 때 검색하게 하는 방식입니다.

Spakky의 기본 DX는 작은 네 계약으로 끝납니다. 애플리케이션은 `IRetriever` 하나를
구현해 기존 지식 검색 경계에 연결하고, 고전적인 RAG에는 `RetrievalContext`, agentic
RAG에는 `RetrievalTool`을 생성자 주입합니다. 검색 저장소를 바꾸어도 Agent 코드는 그대로
둘 수 있습니다.

| 선택 | 검색 시점 | model에 들어가는 형태 |
| --- | --- | --- |
| `RetrievalContext` | 첫 model request 전 | budgeted `AgentContext` evidence |
| `RetrievalTool` | model이 `search(query=...)`를 호출할 때 | 일반 `TOOL` result history |

별도의 RAG 플러그인은 없습니다. 기본 계약은 `spakky-agent`에 포함됩니다.

```bash
pip install spakky-agent
```

## 한 번 구현하고 두 방식으로 주입하기

다음 한 파일은 custom `IRetriever`, classic context, agentic tool을 모두 조립하는 형태입니다.
예제의 고정된 한 건은 계약을 바로 실행해 보기 위한 값입니다. 제품에서는
`SupportRetriever.retrieve()` 본문만 애플리케이션이나 vendor가 소유한 기존 검색
경계 호출로 교체합니다.

```python
from collections.abc import Sequence
from typing import override

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    IAgentModel,
    IRetriever,
    JsonObject,
    RetrievalContext,
    RetrievalHit,
    RetrievalTool,
)
from spakky.core.pod.annotations.pod import Pod


@Pod()
class SupportRetriever(IRetriever):
    @override
    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]:
        if (
            not query.strip()
            or tenant_id != "tenant-42"
            or namespace != "support"
            or filters != {"visibility": "published"}
        ):
            return ()
        return (
            RetrievalHit(
                id="faq-7",
                content="환불 요청은 결제 후 7일 안에 접수할 수 있습니다.",
                source="kb:faq-7",
                score=0.93,
                content_digest="sha256:faq-7-v3",
                revision="2026-08-23",
                tenant_id=tenant_id,
                namespace=namespace,
                start_offset=0,
                end_offset=34,
            ),
        )[:limit]


@Pod()
def support_context(retriever: SupportRetriever) -> RetrievalContext:
    return RetrievalContext(
        retriever,
        tenant_id="tenant-42",
        namespace="support",
        filters={"visibility": "published"},
    )


@Agent(
    spec=AgentExecutionSpec(
        name="support_classic",
        instructions="검색 context에 있는 근거만 사용해 답하세요.",
    )
)
class SupportClassicAgent:
    def __init__(
        self,
        model: IAgentModel,
        retrieval: RetrievalContext,
    ) -> None:
        self._model = model
        self._retrieval = retrieval


@Pod()
def support_search(retriever: SupportRetriever) -> RetrievalTool:
    return RetrievalTool(
        retriever,
        name="search",
        tenant_id="tenant-42",
        namespace="support",
        filters={"visibility": "published"},
    )


@Agent(
    spec=AgentExecutionSpec(
        name="support_agentic",
        instructions="답변에 근거가 필요하면 search tool을 먼저 사용하세요.",
    )
)
class SupportAgenticAgent:
    def __init__(
        self,
        model: IAgentModel,
        retrieval: RetrievalTool,
    ) -> None:
        self._model = model
        self._retrieval = retrieval
```

두 adapter 모두 `limit=5`가 기본입니다. `tenant_id`, `namespace`, `filters`는 생성할 때
고정되고 filters는 중첩 JSON까지 복사됩니다. Model은 이 scope를 인자로 보거나 덮어쓸
수 없습니다. 명시하지 않은 scope는 wildcard가 아닙니다. Unscoped adapter는 unscoped hit만,
scope를 명시한 adapter는 같은 `tenant_id`와 `namespace`를 가진 hit만 받아들입니다.

Classic 경로는 `RunAgentInput.instruction` 전체를 query로 사용합니다. 기본
`refresh_context_each_step=False`에서는 invocation의 첫 결과를 뒤 model step에서도
재사용하고, spec을 `True`로 설정한 Agent만 model step마다 다시 조회합니다. Agentic
경로의 tool schema에는 `query: str` 하나만 노출됩니다. Tool 이름이 Agent의 다른 tool과
겹치면 runner 구성 시 fail closed하므로 애플리케이션 안에서 고유한 이름을 사용합니다.

## 실제 애플리케이션에서 실행하기

위 코드를 `my_app/rag.py`에 두었다고 가정하면, 다음 `main.py`가 plugin load, component
scan, Agent resolve, model 선택과 결과 수집까지 잇는 최소 실행 파일입니다. 이 예제는
[LLM 모델 라우팅](llm-routing.md)의 `support/primary` catalog가 환경변수 또는 Python
설정으로 구성되어 있다고 가정합니다.

```python
import asyncio

import my_app
import spakky.agent
import spakky.plugins.llm
from my_app.rag import SupportAgenticAgent, SupportClassicAgent
from spakky.agent import AgentYieldKind, ModelSelection, RunAgentInput
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


async def main() -> None:
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.agent.PLUGIN_NAME,
                spakky.plugins.llm.PLUGIN_NAME,
            }
        )
        .scan(my_app)
        .start()
    )

    classic = app.container.get(type_=SupportClassicAgent)
    classic_text: list[str] = []
    async for item in classic.execute(
        RunAgentInput(
            state_id="classic-1",
            instruction="환불은 언제까지 신청할 수 있나요?",
            model_selection=ModelSelection(model_ref="support/primary"),
        )
    ):
        if item.kind is AgentYieldKind.TOKEN:
            classic_text.append(item.payload.text)
    print("classic:", "".join(classic_text))

    agentic = app.container.get(type_=SupportAgenticAgent)
    agentic_text: list[str] = []
    async for item in agentic.execute(
        RunAgentInput(
            state_id="agentic-1",
            instruction="FAQ를 검색해서 환불 기한을 알려주세요.",
            model_selection=ModelSelection(model_ref="support/primary"),
        )
    ):
        if item.kind is AgentYieldKind.TOOL:
            print("tool:", item.payload.name, item.payload.result)
        elif item.kind is AgentYieldKind.TOKEN:
            agentic_text.append(item.payload.text)
    print("agentic:", "".join(agentic_text))


asyncio.run(main())
```

Classic Agent에서는 runner가 첫 model request 전에 `SupportRetriever.retrieve()`를 한 번
호출하고, 반환한 hit를 `ModelRequest.context`에 넣습니다. 따라서 일반적으로 `TOOL` yield가
없습니다. Agentic Agent에서는 model이 `search`를 선택한 경우에만 `TOOL` yield가 생기고,
그 JSON 결과가 다음 model step의 history가 됩니다. `instructions`는 model에게 검색 시점을
안내하지만 강제 게이트는 아닙니다. 반드시 매 요청마다 검색해야 한다면 Agentic 경로가
아니라 Classic `RetrievalContext`를 선택합니다.

`Final.output`은 `output_type`을 선언하지 않은 runner-backed Agent에서 실행 요약
`AgentRunResult`입니다. 실제 자연어 답변은 위 예제처럼 `TOKEN` yield를 모으거나 AG-UI/A2A
message delta를 그대로 client에 전달합니다. Typed final object가 필요하면
[AI Agent 개발](agents.md#typed-structured-output)의 `output_type`을 함께 사용합니다.

## Classic RAG: 검색 결과를 context로 넣기

`RetrievalContext`의 기본값은 다음과 같습니다.

| 설정 | 기본값 | 의미 |
| --- | --- | --- |
| `limit` | `5` | 정렬된 hit를 최대 다섯 건 사용 |
| `max_context_tokens` | `2048` | 모든 retrieval pack이 공유하는 총 budget |
| `allow_empty` | `False` | 검색 결과가 없으면 model 호출 전에 실패 |

빈 결과에도 일반 model 답변을 허용하려는 경우에만
`RetrievalContext(retriever, allow_empty=True)`를 명시합니다. 기본 fail-closed 동작은 검색
근거가 필요한 Agent가 근거 없이 답하는 일을 막습니다.

각 hit는 source frame과 content가 한 `EVIDENCE` pack으로 만들어집니다. 위 예제의 첫 줄은
의미상 다음 JSON이며 실제 model content에서는 compact JSON 한 줄 뒤에 검색 content가
붙습니다.

```json
{
  "retrieval": {
    "content_digest": "sha256:faq-7-v3",
    "id": "faq-7",
    "namespace": "support",
    "revision": "2026-08-23",
    "source": "kb:faq-7",
    "span": "0:34",
    "tenant_id": "tenant-42"
  }
}
```

Source frame을 포함한 전체 문자열은 4 characters/token으로 추정됩니다. Ordered hit에 총
`max_context_tokens`를 앞에서부터 배분하고, runner의 context preparation이 각 배분량을
넘는 content를 결정적으로 자릅니다. 따라서 이 값은 provider tokenizer의 정확한 사용량
또는 hard token guarantee가 아니라 model-bound context를 일관되게 자르기 위한
deterministic heuristic입니다.

Classic durable evidence에는 raw 검색 content를 저장하지 않습니다. Pack identity, source,
budget, manifest reference와 검증된 retrieval reference만 남기고 context fingerprint로
동일 step의 evidence를 결속합니다. `RetrievalHit.metadata`의 임의 값은 model context나
evidence로 전달하지 않습니다.

## Agentic RAG: 같은 retriever를 tool로 열기

`RetrievalTool`은 injected `IAgentToolProvider`입니다. Runner가 그 catalog를 Agent의
`@agent_tool`과 합치고, model이 `search(query=...)`를 선택하면 같은 `IRetriever`를
호출합니다. 이 tool은 read-only, idempotent, approval 불필요로 선언되어 있습니다.

검색 결과는 일반 tool 결과와 똑같이 assistant tool-call 뒤의 `TOOL` message에 JSON으로
들어가 다음 model step으로 이어집니다. 반환되는 필드는 hit identity/content/source,
score, revision/digest, scope와 span이며 `RetrievalHit.metadata`는 제외됩니다. 빈 결과는
빈 배열로 돌아가고 model이 다음 판단을 합니다.

이 경로에는 `max_context_tokens`가 없습니다. 검색 content는 일반 tool result처럼 raw
history와 durable tool evidence/checkpoint에 들어가므로, retriever가 model과 저장소에
노출해도 되는 content만 반환하고 크기도 직접 제한해야 합니다. Classic context의
privacy-safe evidence 규칙이 agentic tool result를 자동으로 redaction하거나 줄여 주지는
않습니다.

## 실패 경계

`RetrievalHit`와 adapter를 직접 만들거나 호출하는 경계에서는 잘못된 값이
`AgentRetrievalError`입니다. Blank query/ID/content/source, non-finite score, 불완전한 span,
JSON이 아닌 filter, duplicate ID, 잘못된 result type, bound scope와 다른 hit를 모두
fail closed합니다.

Runner 안에서는 같은 원인이 실행 표면에 맞게 typed terminal code로 정규화됩니다.

| 경계 | terminal code |
| --- | --- |
| `RetrievalContext` 조회·결과 검증 실패 | `agent_model_execution_failed` |
| `RetrievalTool` 실행·결과 직렬화 실패 | `agent_tool_execution_failed` |
| model tool 인자가 missing/extra라 signature에 bind되지 않는 whole-batch validation | `agent_tool_batch_invalid` |
| retrieval await가 run deadline을 넘음 | `agent_timeout` |

Classic 실패는 provider request 전에 끝나고, 잘못된 agentic tool batch는 어떤 tool도
dispatch하기 전에 끝납니다.

## 확장할 때

Vector search나 reranking이 필요하면 Agent와 adapter 계약은 바꾸지 않고 `IRetriever`
구현만 합성합니다. `ITextEmbedding`, `IVectorSearch`, `VectorRetriever`, optional
`IReranker`/`RerankedRetriever`와 Google embedding 구성은
[AI Agent 심화](agents-advanced.md#retrieval-extension-ports)에서 다룹니다.
Tenant/user scope, TTL와 correction이 필요한 long-term memory는 같은 `IRetriever`를
구현하는 `MemoryRetriever`를 사용하며
[Agent Memory, Evaluation, Cost와 Telemetry](agent-operations.md)에서 구성합니다.

Framework는 vector backend, 임시 fallback, index write API를 제공하지 않습니다.
애플리케이션 또는 vendor가 기존 knowledge와 검색 index의 저장·갱신을 소유합니다.
Hit의 순서와 source/revision/content digest 값도 retriever가 소유합니다. Framework는 값의
shape, duplicate, exact scope와 deterministic framing을 검증하지만 backend content를 다시
읽어 digest를 재계산하지는 않습니다.

## 설계 맥락

아래 링크는 API 호환성 주장이 아니라 RAG 흐름을 비교하기 위한 공식 참고 자료입니다.

- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [LangChain — Retrieval](https://docs.langchain.com/oss/python/deepagents/retrieval)
- [Pydantic AI — RAG example](https://pydantic.dev/docs/ai/examples/data-analytics/rag/)

## 함께 보기

- [AI Agent 개발](agents.md): runner-backed Agent와 constructor DI의 기본을 확인합니다.
- [AI Agent 심화](agents-advanced.md): context privacy, tool history, vector/reranking 확장을 확인합니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): retrieval contract의 실제 signature를 확인합니다.
- [spakky-llm API Reference](../api/plugins/spakky-llm.md): Google embedding adapter의 route와 오류 경계를 확인합니다.
