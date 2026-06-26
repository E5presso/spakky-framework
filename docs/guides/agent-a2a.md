# A2A 어댑터

> 선언형 Agent를 A2A(Agent-to-Agent) AgentCard와 task transport로 노출하고, 원격 A2A Agent를 teammate delegation 경로로 호출하는 어댑터 가이드입니다.

`spakky-a2a`는 공식 `a2a-sdk` 타입을 사용합니다. 서버 쪽은 `AgentRunner.run_events()`의 protocol-neutral `AgentEvent` stream을 A2A task/message/artifact update로 투영하고, 클라이언트 쪽은 원격 A2A stream을 child `AgentEvent`로 되돌려 parent run에 합류시킵니다.

## 설치

```bash
pip install spakky-a2a
```

`spakky[agent]` extra에도 `spakky-a2a`가 포함됩니다.

## 서버로 노출

`@A2AAgentServer`는 `@Agent` class에 붙는 marker입니다. `@Agent`가 Pod 등록을 담당하고, A2A marker는 AgentCard에 광고할 base URL과 version만 기록합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec
from spakky.plugins.a2a import A2AAgentServer


@A2AAgentServer(base_url="https://agents.example.com/a2a", version="1.0.0")
@Agent(spec=AgentExecutionSpec(name="assistant", objective="answer with tools"))
class AssistantAgent:
    ...
```

plugin 초기화는 `A2AConfig`, `A2AAgentRegistry`, `A2AAgentServerSpec`, `RegisterA2AAgentServersPostProcessor`를 등록합니다. 부트스트랩 후 `@A2AAgentServer`와 `@Agent`가 모두 붙은 Pod는 registry에 agent name 기준으로 들어갑니다.

`A2AConfig`는 `SPAKKY_A2A_` 접두사의 환경변수를 읽습니다. 이 값은 `@A2AAgentServer`가 `base_url` 또는 `version`을 직접 지정하지 않을 때 derived AgentCard 기본값으로 사용됩니다.

| 환경변수 | 의미 | 기본값 |
| --- | --- | --- |
| `SPAKKY_A2A_DEFAULT_BASE_URL` | AgentCard transport interface에 광고할 base URL | `http://localhost:8000` |
| `SPAKKY_A2A_DEFAULT_VERSION` | AgentCard에 광고할 semantic version | `1.0.0` |

```python
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec

spec = application.container.get(A2AAgentServerSpec)
a2a_app = spec.build_app_for("assistant")
```

이 방식은 registry에 등록된 metadata를 사용해 Starlette app을 만듭니다. agent instance를 직접 들고 있다면 builder를 호출할 수 있습니다.

```python
from spakky.plugins.a2a.server.builder import build_a2a_app

a2a_app = build_a2a_app(
    assistant,
    base_url="https://agents.example.com/a2a",
    version="1.0.0",
)
```

## Transport 선택

`build_a2a_app()`은 AgentCard route와 JSON-RPC route를 함께 가진 mountable Starlette app을 만듭니다. HTTP+JSON REST 또는 gRPC가 필요하면 transport별 builder를 사용합니다.

| transport | builder | 설명 |
|-----------|---------|------|
| JSON-RPC + AgentCard | `build_a2a_app()` | `a2a-sdk` JSON-RPC route와 AgentCard route를 노출합니다. |
| HTTP+JSON REST + AgentCard | `build_a2a_rest_app()` | REST operation route와 AgentCard route를 노출합니다. |
| gRPC | `build_a2a_grpc_handler()` | 공식 `lf.a2a.v1.A2AService` generic gRPC handler를 만듭니다. |

```python
from spakky.plugins.a2a.rest_transport.builder import build_a2a_rest_app
from spakky.plugins.a2a.grpc_transport import build_a2a_grpc_handler

rest_app = build_a2a_rest_app(
    assistant,
    base_url="https://agents.example.com/a2a",
    version="1.0.0",
    path_prefix="/v1",
)
grpc_handler = build_a2a_grpc_handler(
    assistant,
    base_url="https://agents.example.com/a2a-grpc",
    version="1.0.0",
)
```

## AgentCard derivation

`AgentCardFactory`는 `@Agent` spec, tool catalog, teammate 선언으로 `AgentCard`를 만듭니다.

| 입력 | AgentCard 반영 |
|------|----------------|
| `AgentExecutionSpec.name` | card name. 없으면 class name |
| `objective` 또는 `instructions` | card description |
| `streaming_exposure_mode` | `NO_STREAM_UNTIL_FINAL_GUARDED`가 아니면 streaming true |
| `@agent_tool` descriptor | JSON input/output skill |
| `AgentTeammate` | `delegation` tag가 붙은 teammate skill |

## Task 저장소

서버 builder의 `repository` 인자는 optional `IA2ATaskRepository`입니다. 지정하지 않으면 `InMemoryA2ATaskRepository`가 사용됩니다. 운영에서 durable task state가 필요하면 `IA2ATaskRepository` 구현을 Pod나 builder 인자로 제공합니다.

```python
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository
from spakky.plugins.a2a.server.builder import build_a2a_app

repository = application.container.get(IA2ATaskRepository)
a2a_app = build_a2a_app(
    assistant,
    base_url="https://agents.example.com/a2a",
    version="1.0.0",
    repository=repository,
)
```

`SpakkyA2ATaskStore`는 synchronous repository를 `a2a-sdk`의 async `TaskStore`로 감싸는 bridge입니다.
이 저장소는 A2A protocol `Task` snapshot을 보존합니다. Agent 대화 transcript를
`conversation_id`로 재생하는 core `ITaskStore`와는 별도 책임입니다.

## Event projection

A2A executor는 inbound task id를 core `RunAgentInput.state_id`로 사용하고, A2A `context_id`를 `RunAgentInput.conversation_id`로 넘깁니다. 그 뒤 `AgentRunner.run_events()`를 순회해 task update로 투영합니다.

| `AgentEvent` | A2A 투영 |
|--------------|----------|
| `RUN_STARTED` | task working |
| `MESSAGE_DELTA`, `REASONING_DELTA` | working status message |
| `TOOL_CALL_*` | working metadata 또는 artifact |
| `RUN_PAUSED` | `input-required` 또는 `auth-required` |
| `RUN_FINISHED` | executor가 stream drain 후 complete 또는 failed로 reconcile |
| `STATE_SNAPSHOT`, `STATE_DELTA`, `ARTIFACT` | data part 또는 artifact |

승인 재개는 inbound A2A data part에 `approval_id`와 `decision`을 담아 보냅니다. executor는 이를 `APPROVAL_DECISION` signal로 append하고 `RunAgentInput(resume=True)`로 runner를 재개합니다.

## Teammate 위임

`AgentExecutionSpec.teammates`에 선언한 teammate는 runner가 model-callable delegation tool로 노출합니다. tool schema 이름은 `teammate.<schema_token(name)>.delegate`입니다. `schema_token`은 teammate name을 소문자화하고 `[a-zA-Z0-9_]`가 아닌 문자를 `_`로 치환한 값입니다.

로컬 teammate는 parent agent에 teammate Pod 인스턴스를 주입하면 in-process로 실행됩니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, AgentTeammate


@Agent(spec=AgentExecutionSpec(name="researcher"))
class ResearcherAgent:
    ...


@Agent(
    spec=AgentExecutionSpec(
        name="orchestrator",
        delegation_allowed=True,
        teammates=(AgentTeammate(name="researcher", pod=ResearcherAgent),),
    )
)
class OrchestratorAgent:
    def __init__(self, researcher: ResearcherAgent) -> None:
        self._researcher = researcher
```

원격 teammate는 AgentCard URL을 선언하고 `A2AAgentDelegate`를 parent agent에 주입합니다. delegate는 AgentCard를 fetch한 뒤 SDK client로 message stream을 수행하고, remote task/message/artifact update를 neutral child event로 되돌립니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, AgentTeammate
from spakky.plugins.a2a import A2AAgentDelegate


@Agent(
    spec=AgentExecutionSpec(
        name="orchestrator",
        delegation_allowed=True,
        teammates=(
            AgentTeammate(
                name="remote_reviewer",
                card_url="https://reviewer.example/.well-known/agent-card.json",
            ),
        ),
    )
)
class OrchestratorAgent:
    def __init__(self, delegate: A2AAgentDelegate) -> None:
        self._delegate = delegate
```

`A2ARemoteAgentClient.resolve_card()`는 URL path가 비어 있으면 `/.well-known/agent-card.json`을 사용합니다. `RemoteA2AMessage`는 text, optional task/context id, message id를 담는 송신 envelope입니다.

## API Reference

- [spakky-a2a API Reference](../api/plugins/spakky-a2a.md): server builder, REST/gRPC transport, executor, store, client, delegation API를 확인합니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): `AgentTeammate`, `AgentEvent`, `RunAgentInput`, delegation 타입을 확인합니다.
