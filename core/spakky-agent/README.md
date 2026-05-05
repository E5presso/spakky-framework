# spakky-agent

`spakky-agent`는 ADR-0009 Agentic Hexagonal Architecture의 core contract 패키지입니다. Agent를 LLM SDK wrapper가 아니라 `@UseCase`와 같은 application workflow component로 다루기 위한 public 타입 표면을 제공합니다.

## 언제 필요한가

- agentic workflow를 Spakky DI/hexagonal architecture 안에서 표현하려는 경우
- `AgentYield` stream을 FastAPI, WebSocket, CLI 같은 inbound adapter가 직접 소비하게 하려는 경우
- model adapter를 `IAgentModel` outbound port로 구현하려는 경우
- long-running execution의 state, signal, evidence 계약을 plugin contribution으로 구현하려는 경우

## 제공하는 public surface

- `Agent`, `AgentExecutionSpec`, `AgentExecutionLimits`: `@UseCase`와 동격인 Pod stereotype과 보조 실행 의미
- `AgentYield`: `execute()`가 caller에게 흘려보내는 typed stream item
- `AgentState`: long-running agent execution의 materialized lifecycle state
- `AgentSignal`: 실행 중 들어오는 user message, approval, cancel 같은 inbound stimulus
- `AgentEvidence`: tool/model/context 판단 근거를 위한 append-only artifact
- `ContextPack`, `ContextManifest`, `ContextDigest`: model input context와 audit/digest evidence를 위한 typed contract
- `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`: persistence provider가 구현하는 core port
- `IAgentModel`: vLLM 등 model backend가 구현하는 outbound port
- `ModelRequest`, `ModelResponse`, `ModelStreamEvent`: provider-neutral model 호출/응답/stream 계약
- `ToolCallingSpec`, `ModelToolSpec`, `ModelToolCall`: model-facing tool call 요청과 후보 결과

## 의존성 경계

Core package는 `spakky` core에만 의존합니다. vLLM, SQLAlchemy, FastAPI, Typer 같은 infrastructure dependency를 직접 import하지 않습니다.

Production persistence fallback도 제공하지 않습니다. State, signal, evidence repository 구현은 SQLAlchemy 등 provider plugin의 feature contribution으로 등록되어야 하며, 누락 시 bootstrap 단계에서 custom error로 실패해야 합니다.

`AgentEvidenceRepository`의 agent-facing interface는 append/read 계열만 노출합니다. Redaction, correction, context digest 갱신은 기존 evidence를 수정하지 않고 새 evidence를 append하는 방식으로 표현합니다.

## 사용 예시

```python
from collections.abc import AsyncGenerator

from spakky.agent import (
    Agent,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentSignalKind,
    AgentYield,
    AgentYieldKind,
    Final,
    IAgentModel,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEventKind,
    Token,
)


@Agent(
    spec=AgentExecutionSpec(
        name="code_assistant",
        objective="inspect and edit a workspace",
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ),
        limits=AgentExecutionLimits(timeout_seconds=300),
    )
)
class CodeAssistant:
    def __init__(self, model: IAgentModel) -> None:
        self.model = model

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        request = ModelRequest(
            messages=(ModelMessage(ModelMessageRole.USER, command),),
        )
        async for event in self.model.stream(request):
            if event.kind == ModelStreamEventKind.TOKEN_DELTA:
                yield AgentYield(
                    kind=AgentYieldKind.TOKEN,
                    payload=Token(event.token_delta or ""),
                )

        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )
```

`@Agent`는 `@Pod` 계열 stereotype이므로 application scan과 constructor DI에 참여합니다. `execute()`는 `Generator[AgentYield[T], None, None]` 또는 `AsyncGenerator[AgentYield[T], None]`로 typed stream item을 yield할 수 있고, non-generator 반환형은 streaming 없는 직접 결과 계약으로 취급됩니다. Inbound adapter가 SSE/WebSocket/CLI처럼 진행 상태를 즉시 내보내야 한다면 `AgentYield` generator 계약을 사용해야 합니다.

`AgentYieldKind`의 public status vocabulary는 `token`, `progress`, `tool`, `evidence`, `approval`, `final`, `error`, `cancel`입니다. 각 item의 payload는 `Token`, `Progress`, `Tool`, `Evidence`, `Approval`, `Final[T]`, `Error`, `Cancel` value object로 구분되므로 inbound adapter는 별도 stream projector 없이 generator를 직접 순회해 transport별 이벤트로 바꿀 수 있습니다.

잘못된 signature나 지원하지 않는 metadata는 definition/bootstrap 단계에서 `AgentDefinitionError` 또는 `AgentBootstrapError`로 드러납니다.

`IAgentModel.stream()`은 model adapter가 token delta, tool-call candidate, structured output, error, done을 `ModelStreamEventKind`로 구분해 내보내는 계약입니다. 실제 vLLM/OpenAI-compatible HTTP 연결은 `plugins/spakky-vllm` 같은 outbound adapter가 담당하며, core package에는 production model implementation을 넣지 않습니다.

## Context contract

Model input context는 raw 문자열을 이어 붙인 prompt snapshot이 아니라 `ContextPack` sequence로 전달합니다. 각 pack은 source, role, freshness, relevance, token budget, sensitivity metadata를 보존하고, `ContextManifest`는 pack 구성과 origin/evidence reference를 audit 단위로 남깁니다. 압축이나 요약은 원본 evidence를 대체하지 않고 `ContextDigest` derived evidence로 표현합니다.

`ModelRequest.assemble_messages()`는 기존 `messages`와 `context` packs를 provider-neutral `ModelMessage` tuple로 조립하는 hook입니다. Adapter는 이 hook을 사용해 context metadata를 잃지 않고 provider payload로 변환할 수 있습니다.
