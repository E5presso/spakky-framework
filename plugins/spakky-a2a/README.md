# spakky-a2a

A2A (Agent2Agent) protocol server plugin for the Spakky framework.

## Remote teammate delegation

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
        self._delegate = delegate
```

Remote delegation sends `message/send` through the SDK client, tracks the remote
task stream, and maps child task/message/artifact updates back into Spakky's
protocol-neutral event stream with the parent run id preserved.

## REST HTTP+JSON transport

`build_a2a_rest_app()` builds a mountable Starlette app for the official A2A
HTTP+JSON binding. The transport reuses the same AgentCard derivation,
`TaskStore`, `SpakkyAgentExecutor`, and neutral agent-event projection used by
the JSON-RPC and gRPC transports.

```python
from spakky.plugins.a2a.rest_transport import build_a2a_rest_app

app = build_a2a_rest_app(
    assistant_agent,
    base_url="https://agents.example.com/a2a",
    version="1.0.0",
)
```

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

## HITL and auth interrupts

`SpakkyAgentExecutor` consumes the core `AgentRunner.run_events()` stream. Approval
and auth pauses arrive as protocol-neutral `RunPausedEvent` items rather than as
successful `RunFinishedEvent` terminals. The A2A projector maps
`reason=approval_required` to `TASK_STATE_INPUT_REQUIRED` and includes the
approval id plus allowed decisions in a data part. It maps `reason=auth_required`
to `TASK_STATE_AUTH_REQUIRED`, so auth-required is reachable without inspecting
durable `state.reason` after the run stream drains.

## gRPC transport

`build_a2a_grpc_handler()` builds a `grpc.GenericRpcHandler` for the official
`lf.a2a.v1.A2AService` descriptor. The transport exposes:

- `SendMessage`
- `SendStreamingMessage`
- `GetTask`
- `CancelTask`

The gRPC handler reuses the same AgentCard derivation, `TaskStore`,
`SpakkyAgentExecutor`, and neutral agent-event projection used by the JSON-RPC
transport. Add the handler to a `spakky-grpc` `GrpcServerSpec` or another
`grpc.aio.Server`, then call `/lf.a2a.v1.A2AService/<Method>` with the protobuf
message classes provided by `a2a-sdk`.
