# A2A 어댑터

> 선언형 Agent를 A2A(Agent-to-Agent) AgentCard와 task transport로 노출하고, 원격 A2A Agent를 teammate delegation 경로로 호출하는 어댑터 가이드입니다.

`spakky-a2a`는 공식 `a2a-sdk` 타입을 사용합니다. 서버 쪽은 `AgentRunner.run_events()`의 protocol-neutral `AgentEvent` stream을 A2A task/message/artifact update로 투영하고, 클라이언트 쪽은 원격 A2A stream을 child `AgentEvent`로 되돌려 parent run에 합류시킵니다.

## 설치

```bash
pip install spakky-a2a
```

`spakky[agent]` extra에도 `spakky-a2a`가 포함됩니다.

## 서버로 노출

`@A2ACompatible`는 `@Agent` class에 붙는 marker입니다. `@Agent`가 Pod 등록을 담당하고, A2A marker는 AgentCard에 광고할 public transport URL/version과 optional ASGI/gRPC exposure metadata를 기록합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec
from spakky.plugins.a2a import A2ACompatible


@A2ACompatible(
    base_url="https://agents.example.com/a2a/assistant",
    version="1.0.0",
    mount_path="/a2a/assistant",
    rest_mount_path="/a2a-rest/assistant",
    rest_base_url="https://agents.example.com/a2a-rest/assistant",
    grpc_enabled=True,
    grpc_base_url="grpc://agents.example.com:443",
)
@Agent(spec=AgentExecutionSpec(name="assistant", objective="answer with tools"))
class AssistantAgent:
    ...
```

plugin 초기화는 `A2AConfig`, `A2AAgentRegistry`, `A2AAgentServerSpec`, `RegisterA2AAgentServersPostProcessor`, ASGI mount post-processor, gRPC registration post-processor, remote delegate Pod를 등록합니다. 부트스트랩 후 `@A2ACompatible`와 `@Agent`가 모두 붙은 Pod는 registry에 agent name 기준으로 들어가고, Starlette/FastAPI host Pod가 있으면 자동으로 mount됩니다. `spakky-grpc`가 함께 로드되어 `GrpcServerSpec`가 있으면 `grpc_enabled=True` entry의 gRPC handler도 자동 등록됩니다.

`A2AConfig`는 `SPAKKY_A2A_` 접두사의 환경변수를 읽습니다. `default_base_url`은 marker가 `base_url`을 생략할 때 실제 mount path와 결합되어 AgentCard interface URL을 유도합니다.

| 환경변수 | 의미 | 기본값 |
| --- | --- | --- |
| `SPAKKY_A2A_DEFAULT_BASE_URL` | mount path와 결합할 public host URL | `http://localhost:8000` |
| `SPAKKY_A2A_DEFAULT_VERSION` | AgentCard에 광고할 semantic version | `1.0.0` |
| `SPAKKY_A2A_DEFAULT_MOUNT_PATH_PREFIX` | 자동 mount path prefix | `/a2a` |

```python
from starlette.applications import Starlette
from spakky.core.pod.annotations.pod import Pod


@Pod(name="asgi_host")
def asgi_host() -> Starlette:
    return Starlette()
```

`mount_path`를 생략하면 `{default_mount_path_prefix}/{agent_name}`을 사용합니다. Bootstrap 후
`/a2a/assistant/.well-known/agent-card.json`과 `/a2a/assistant/` JSON-RPC route가 host app에
존재합니다. `rest_mount_path`를 지정하면 `/a2a-rest/assistant/.well-known/agent-card.json`과
REST operation route가 같은 host app에 추가됩니다.

## Transport 선택

일반 애플리케이션은 transport별 builder 함수를 호출하지 않습니다. 노출할 transport를 `@A2ACompatible` metadata로 선언하고, plugin post-processor가 host에 연결합니다.

| transport | 선언 | 결과 |
|-----------|------|------|
| JSON-RPC + AgentCard | `mount_path` 또는 기본 prefix | Starlette/FastAPI host에 mount |
| HTTP+JSON REST + AgentCard | `rest_mount_path` | Starlette/FastAPI host에 별도 mount |
| gRPC | `grpc_enabled=True`, 선택적 `grpc_base_url` | `spakky-grpc` `GrpcServerSpec`에 handler 등록 |

`base_url`, `rest_base_url`, `grpc_base_url`은 AgentCard에 광고되는 public operation endpoint입니다. ASGI mount path나 reverse proxy prefix가 외부 URL에 보이면 포함해야 합니다. AgentCard discovery path인 `/.well-known/agent-card.json` 자체는 포함하지 않습니다. 값을 생략하면 JSON-RPC는 `default_base_url + mount_path`, REST는 `default_base_url + rest_mount_path`를 사용합니다. gRPC는 HTTP path 기반 mount가 아니므로 실제 listener/scheme이 다르면 `grpc_base_url`을 명시합니다.

`A2AAgentServerSpec.build_app_for()`, `build_rest_app_for()`, `build_grpc_handler_for()`와 transport builder 함수들은 custom host와 테스트를 위한 lower-level API입니다.

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

서버 transport는 container에서 optional `IA2ATaskRepository` Pod를 찾습니다. 등록된 repository가 없으면 `InMemoryA2ATaskRepository`가 사용됩니다. 운영에서 durable task state가 필요하면 repository 구현을 Pod로 등록합니다.

```python
from collections.abc import Sequence
from a2a.types import Task
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository


@Pod()
class PostgresA2ATaskRepository(IA2ATaskRepository):
    def get_or_none(self, task_id: str) -> Task | None:
        ...

    def save(self, task: Task) -> None:
        ...

    def delete(self, task_id: str) -> None:
        ...

    def list_all(self) -> Sequence[Task]:
        ...
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

A2A client가 사용자별 model/provider 선택이나 MCP 서버 선택을 함께 전달해야 하면 message data part를 사용합니다. Executor는 `modelSelection` 또는 `model_selection`을 `RunAgentInput.model_selection`으로, `metadata`와 `mcp` object를 `RunAgentInput.metadata`로 변환합니다.

```json
{
  "modelSelection": {
    "provider": "openrouter",
    "model": "anthropic/claude-sonnet-4.5",
    "profile": "coding",
    "metadata": {"tier": "paid"}
  },
  "mcp": {
    "servers": ["github"]
  },
  "metadata": {
    "tenant": "acme"
  }
}
```

`mcp.servers`에는 `McpConfig.servers`에 선언된 서버 이름 또는 inline MCP server declaration을 넣습니다. 같은 run 안에서 같은 MCP server `name`을 두 번 선택하면 도구 prefix와 credential 선택이 모호하므로 `McpServerConfigurationError`로 실패합니다.

## Teammate 위임

`AgentExecutionSpec.teammates`에 선언한 teammate는 runner가 model-callable delegation tool로 노출합니다. tool schema 이름은 `teammate.<schema_token(name)>.delegate`입니다. `schema_token`은 teammate name의 앞뒤 공백을 제거한 뒤 `[a-zA-Z0-9_]`가 아닌 연속 문자를 단일 `_`로 치환하고, 앞뒤 `_`를 제거한 다음 소문자화한 값입니다. 이 결과가 비면 agent definition 단계에서 거부됩니다.

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
