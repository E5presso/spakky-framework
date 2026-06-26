# spakky-a2a

A2A (Agent2Agent) protocol server and delegation plugin for `spakky-agent`.
It exposes a Spakky `@Agent` as an A2A server, derives an AgentCard from the
agent spec/tool catalog/teammates, and implements the core `IAgentDelegate` port
for remote teammate calls over the official `a2a-sdk` client.

## Installation

```bash
pip install spakky-a2a
```

An executable agent still needs an `IAgentModel` provider and, for durable runs
or HITL resume, the `spakky-agent` persistence repositories supplied by a
provider such as `spakky-sqlalchemy[agent]`.

## Configuration

`A2AConfig` reads `SPAKKY_A2A_` environment variables.

| Environment variable | Default | Purpose |
|----------------------|---------|---------|
| `SPAKKY_A2A_DEFAULT_BASE_URL` | `http://localhost:8000` | Base URL advertised on derived AgentCard interfaces when an app uses the default config |
| `SPAKKY_A2A_DEFAULT_VERSION` | `1.0.0` | Semantic version advertised on derived AgentCards |

Plugin initialization registers `A2AConfig`, `A2AAgentRegistry`,
`A2AAgentServerSpec`, and the post-processor that discovers classes carrying both
`@Agent` and `@A2AAgentServer`.

## Exposing an Agent

`@A2AAgentServer` is a tag stacked on the same class as `@Agent`; `@Agent`
registers the Pod, while the tag records A2A transport metadata.

```python
from spakky.agent import Agent, AgentExecutionSpec, IAgentModel
from spakky.plugins.a2a import A2AAgentServer


@A2AAgentServer(base_url="https://agents.example.com/a2a", version="1.0.0")
@Agent(spec=AgentExecutionSpec(name="planner", objective="Plan work"))
class PlannerAgent:
    def __init__(self, model: IAgentModel) -> None:
        self.model = model
```

After application bootstrap, `A2AAgentServerSpec.build_app_for("planner")`
resolves the registered agent, uses a container-provided `IA2ATaskRepository`
when one is registered, and falls back to an in-memory task repository otherwise.

For direct assembly, use the transport-specific builders:

```python
from spakky.plugins.a2a.server.builder import build_a2a_app
from spakky.plugins.a2a.rest_transport import build_a2a_rest_app
from spakky.plugins.a2a.grpc_transport import build_a2a_grpc_handler

jsonrpc_app = build_a2a_app(agent, base_url="https://agents.example.com/a2a", version="1.0.0")
rest_app = build_a2a_rest_app(agent, base_url="https://agents.example.com/a2a", version="1.0.0")
grpc_handler = build_a2a_grpc_handler(agent, base_url="https://agents.example.com/a2a", version="1.0.0")
```

- `build_a2a_app()` builds a Starlette app with the AgentCard route plus
  JSON-RPC routes from `a2a-sdk` with v0.3 method compatibility.
- `build_a2a_rest_app()` builds the HTTP+JSON REST binding and accepts an
  optional `path_prefix`.
- `build_a2a_grpc_handler()` builds a `grpc.GenericRpcHandler` for
  `lf.a2a.v1.A2AService`.

## AgentCard Derivation

`AgentCardFactory` derives the card from:

- `AgentExecutionSpec.name`, `objective`, or `instructions` for name/description.
- `streaming_exposure_mode`; `NO_STREAM_UNTIL_FINAL_GUARDED` disables streaming
  capability exposure.
- native `@agent_tool` descriptors, excluding synthetic teammate delegation tools.
- declared `AgentTeammate` entries, projected as delegation skills.

## Remote Teammate Delegation

`A2AAgentDelegate` implements the core `IAgentDelegate` port for teammates whose
`AgentExecutionSpec.teammates` entry points at a remote AgentCard URL. The core
agent runner exposes each teammate as a model-callable delegation tool named
`teammate.<name>.delegate`; local teammate pods run in-process, while remote
teammates use the official `a2a-sdk` client.

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

Remote delegation sends `message/send` through the SDK client, tracks the remote
task stream, and maps child task/message/artifact updates back into Spakky's
protocol-neutral event stream with the parent run id preserved.

## REST HTTP+JSON Transport

The SDK route names differ from JSON-RPC method strings:

| A2A operation | REST route |
|---------------|------------|
| `message/send` | `POST /message:send` |
| `message/stream` | `POST /message:stream` |
| `tasks/get` | `GET /tasks/{id}` |
| `tasks/cancel` | `POST /tasks/{id}:cancel` |
| `tasks/subscribe` | `GET /tasks/{id}:subscribe` or `POST /tasks/{id}:subscribe` |

REST request and response bodies use the A2A SDK protobuf JSON encoding. For
example, send a user message with `{"message":{"role":"ROLE_USER","messageId":"m1","parts":[{"text":"hi"}]}}`.

## HITL and Auth Interrupts

`SpakkyAgentExecutor` consumes the core `AgentRunner.run_events()` stream. Approval
and auth pauses arrive as protocol-neutral `RunPausedEvent` items rather than as
successful `RunFinishedEvent` terminals. The A2A projector maps
`reason=approval_required` to `TASK_STATE_INPUT_REQUIRED` and includes the
approval id plus allowed decisions in a data part. It maps `reason=auth_required`
to `TASK_STATE_AUTH_REQUIRED`, so auth-required is reachable without inspecting
durable `state.reason` after the run stream drains.

Approval resume is carried as an inbound A2A data part with `approval_id` and
`decision`; the executor appends an `APPROVAL_DECISION` signal and reruns the
same task id with `RunAgentInput(resume=True)`.

## Task Store

Server transports use `SpakkyA2ATaskStore`, an async `a2a-sdk` `TaskStore` bridge
over the synchronous `IA2ATaskRepository` port. If no repository is supplied to a
builder and no repository Pod is present in the container, the plugin uses
`InMemoryA2ATaskRepository`.

## License

MIT License
