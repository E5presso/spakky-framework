# spakky-a2a

> `spakky-a2a`는 `spakky-agent`를 A2A (Agent2Agent) protocol server와 원격 teammate delegation으로 노출하는 adapter plugin입니다.
> Spakky `@Agent`를 A2A server로 공개하고, agent spec/tool catalog/teammates에서 AgentCard를 유도하며, 공식 `a2a-sdk` client 위에 core `IAgentDelegate` port를 구현합니다.

## 설치

```bash
pip install spakky-a2a
```

실행 가능한 agent에는 별도 `IAgentModel` provider가 필요합니다. Durable run 또는 HITL resume을 사용하면 `spakky-sqlalchemy[agent]` 같은 provider가 공급하는 `spakky-agent` persistence repository도 필요합니다.

## 설정

`A2AConfig`는 `SPAKKY_A2A_` 접두사의 환경변수를 읽습니다.

| 환경변수 | 기본값 | 목적 |
|----------------------|---------|---------|
| `SPAKKY_A2A_DEFAULT_BASE_URL` | `http://localhost:8000` | 기본 config를 쓰는 derived AgentCard interface에 광고할 base URL |
| `SPAKKY_A2A_DEFAULT_VERSION` | `1.0.0` | derived AgentCard에 광고할 semantic version |
| `SPAKKY_A2A_DEFAULT_MOUNT_PATH_PREFIX` | `/a2a` | 자동 mount되는 A2A agent app의 path prefix |

Plugin 초기화는 `A2AConfig`, `A2AAgentRegistry`, `A2AAgentServerSpec`, A2A remote delegate Pod, 그리고 `@Agent`와 `@A2AAgentServer`가 함께 붙은 class를 발견해 ASGI host에 mount하는 post-processor를 등록합니다.

## Agent 노출

`@A2AAgentServer`는 `@Agent`와 같은 class에 쌓는 tag입니다. `@Agent`가 Pod를 등록하고, tag는 A2A transport metadata와 optional mount path를 기록합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, IAgentModel
from spakky.plugins.a2a import A2AAgentServer


@A2AAgentServer(
    base_url="https://agents.example.com/a2a/planner",
    version="1.0.0",
    mount_path="/a2a/planner",
)
@Agent(spec=AgentExecutionSpec(name="planner", objective="Plan work"))
class PlannerAgent:
    def __init__(self, model: IAgentModel) -> None:
        self.model = model
```

애플리케이션이 Starlette/FastAPI host Pod를 제공하면 plugin post-processor가 bootstrap 중
`mount_path`에 A2A JSON-RPC + AgentCard app을 자동 mount합니다. `mount_path`를 생략하면
`{default_mount_path_prefix}/{agent_name}`을 사용합니다. `base_url`과 `version`을 생략하면
`A2AConfig.default_base_url`, `A2AConfig.default_version`을 사용합니다.

```python
from starlette.applications import Starlette
from spakky.core.pod.annotations.pod import Pod


@Pod(name="asgi_host")
def asgi_host() -> Starlette:
    return Starlette()
```

애플리케이션 bootstrap 이후 `A2AAgentServerSpec.build_app_for("planner")`는 등록된 agent를
resolve하는 lower-level API로 사용할 수 있습니다. Container에 `IA2ATaskRepository`가 등록되어
있으면 이를 사용하고, 없으면 `InMemoryA2ATaskRepository`를 사용합니다.

직접 조립해야 하는 host 환경에서는 transport별 builder를 lower-level API로 사용할 수 있습니다.

```python
from spakky.plugins.a2a.server.builder import build_a2a_app
from spakky.plugins.a2a.rest_transport import build_a2a_rest_app
from spakky.plugins.a2a.grpc_transport import build_a2a_grpc_handler

jsonrpc_app = build_a2a_app(agent, base_url="https://agents.example.com/a2a", version="1.0.0")
rest_app = build_a2a_rest_app(agent, base_url="https://agents.example.com/a2a", version="1.0.0")
grpc_handler = build_a2a_grpc_handler(agent, base_url="https://agents.example.com/a2a", version="1.0.0")
```

- `build_a2a_app()`은 AgentCard route와 `a2a-sdk` JSON-RPC route(v0.3 method compatibility 포함)를 가진 Starlette app을 만듭니다.
- `build_a2a_rest_app()`은 HTTP+JSON REST binding을 만들고 optional `path_prefix`를 받습니다.
- `build_a2a_grpc_handler()`는 `lf.a2a.v1.A2AService`용 `grpc.GenericRpcHandler`를 만듭니다.

## AgentCard 유도

`AgentCardFactory`는 다음 입력에서 card를 유도합니다.

- name/description: `AgentExecutionSpec.name`, `objective`, 또는 `instructions`
- streaming capability: `streaming_exposure_mode`; `NO_STREAM_UNTIL_FINAL_GUARDED`는 streaming capability 노출을 끕니다.
- tool: synthetic teammate delegation tool을 제외한 native `@agent_tool` descriptor
- delegation skill: 선언된 `AgentTeammate` entry

## 원격 Teammate 위임

`A2AAgentDelegate`는 `AgentExecutionSpec.teammates` entry가 원격 AgentCard URL을 가리키는 teammate를 위해 core `IAgentDelegate` port를 구현합니다. Plugin 초기화가 `A2AAgentDelegate`를 Pod로 등록하고 `IAgentDelegate`에 바인딩하므로 parent agent는 `IAgentDelegate` 또는 `A2AAgentDelegate`를 생성자 주입으로 받을 수 있습니다. Core agent runner는 각 teammate를 `teammate.<schema_token(name)>.delegate`라는 model-callable delegation tool로 노출합니다. `schema_token`은 teammate name의 앞뒤 공백을 제거한 뒤 `[a-zA-Z0-9_]`가 아닌 연속 문자를 단일 `_`로 치환하고, 앞뒤 `_`를 제거한 다음 소문자화한 값입니다. 이 결과가 비면 agent definition 단계에서 거부됩니다. Local teammate Pod는 in-process로 실행하고, remote teammate는 공식 `a2a-sdk` client를 사용합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, AgentTeammate
from spakky.plugins.a2a import A2AAgentDelegate


@Agent(
    spec=AgentExecutionSpec(
        name="orchestrator",
        teammates=(
            AgentTeammate(
                name="researcher",
                card_url="https://agents.example.com/.well-known/agent-card.json",
            ),
        ),
    )
)
class Orchestrator:
    def __init__(self, delegate: A2AAgentDelegate) -> None:
        self.delegate = delegate
```

원격 delegation은 SDK client로 `message/send`를 보내고 remote task stream을 추적한 뒤, child task/message/artifact update를 parent run id를 보존한 Spakky protocol-neutral event stream으로 되돌립니다.

## REST HTTP+JSON Transport

SDK route 이름은 JSON-RPC method 문자열과 다릅니다.

| A2A operation | REST route |
|---------------|------------|
| `message/send` | `POST /message:send` |
| `message/stream` | `POST /message:stream` |
| `tasks/get` | `GET /tasks/{id}` |
| `tasks/cancel` | `POST /tasks/{id}:cancel` |
| `tasks/subscribe` | `GET /tasks/{id}:subscribe` or `POST /tasks/{id}:subscribe` |

REST request/response body는 A2A SDK protobuf JSON encoding을 사용합니다. 예를 들어 user message는 `{"message":{"role":"ROLE_USER","messageId":"m1","parts":[{"text":"hi"}]}}` 형태로 보냅니다.

## HITL와 Auth Interrupt

`SpakkyAgentExecutor`는 core `AgentRunner.run_events()` stream을 소비합니다. Approval/auth pause는 successful terminal `RunFinishedEvent`가 아니라 protocol-neutral `RunPausedEvent`로 들어옵니다. A2A projector는 `reason=approval_required`를 `TASK_STATE_INPUT_REQUIRED`로 매핑하고 approval id와 allowed decisions를 data part에 포함합니다. `reason=auth_required`는 `TASK_STATE_AUTH_REQUIRED`로 매핑하므로, run stream이 끝난 뒤 durable `state.reason`을 다시 조회하지 않아도 auth-required 상태를 표현할 수 있습니다.

Approval resume은 `approval_id`와 `decision`을 가진 inbound A2A data part로 전달됩니다. Executor는 `APPROVAL_DECISION` signal을 append하고 같은 task id로 `RunAgentInput(resume=True)`를 다시 실행합니다.

## Task Store

Server transport는 synchronous `IA2ATaskRepository` port 위에 async `a2a-sdk` `TaskStore`를 얹는 bridge인 `SpakkyA2ATaskStore`를 사용합니다. Builder 인자로 repository를 주지 않고 container에도 repository Pod가 없으면 plugin은 `InMemoryA2ATaskRepository`를 사용합니다.

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License
