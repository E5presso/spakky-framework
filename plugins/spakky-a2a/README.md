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
| `SPAKKY_A2A_DEFAULT_BASE_URL` | `http://localhost:8000` | marker가 `base_url`을 생략할 때 mount path와 결합할 public host URL |
| `SPAKKY_A2A_DEFAULT_VERSION` | `1.0.0` | derived AgentCard에 광고할 semantic version |
| `SPAKKY_A2A_DEFAULT_MOUNT_PATH_PREFIX` | `/a2a` | 자동 mount되는 A2A agent app의 path prefix |

Plugin 초기화는 `A2AConfig`, `A2AAgentRegistry`, `A2AAgentServerSpec`, A2A remote delegate Pod, 그리고 `@Agent`와 `@A2ACompatible`가 함께 붙은 class를 발견해 ASGI/gRPC host에 연결하는 post-processor를 등록합니다.

## Agent 노출

`@A2ACompatible`는 `@Agent`와 같은 class에 쌓는 tag입니다. `@Agent`가 Pod를 등록하고, tag는 A2A transport metadata와 optional mount path를 기록합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, IAgentModel
from spakky.plugins.a2a import A2ACompatible


@A2ACompatible(
    base_url="https://agents.example.com/a2a/planner",
    version="1.0.0",
    mount_path="/a2a/planner",
    rest_mount_path="/a2a-rest/planner",
    rest_base_url="https://agents.example.com/a2a-rest/planner",
    grpc_enabled=True,
    grpc_base_url="grpc://agents.example.com:443",
)
@Agent(spec=AgentExecutionSpec(name="planner", objective="Plan work"))
class PlannerAgent:
    def __init__(self, model: IAgentModel) -> None:
        self.model = model
```

애플리케이션이 Starlette/FastAPI host Pod를 제공하면 plugin post-processor가 bootstrap 중
`mount_path`에 A2A JSON-RPC + AgentCard app을 자동 mount합니다. `rest_mount_path`를 지정하면
HTTP+JSON REST + AgentCard app도 그 path에 별도로 mount합니다. `mount_path`를 생략하면
`{default_mount_path_prefix}/{agent_name}`을 사용합니다. `version`을 생략하면
`A2AConfig.default_version`을 사용합니다.

`base_url`은 AgentCard `supported_interfaces[].url`에 광고되는 **public transport endpoint**입니다.
클라이언트가 reverse proxy나 ASGI mount path를 통해 호출한다면 그 외부 path를 포함해야 하며,
`/.well-known/agent-card.json` 자체는 포함하지 않습니다. 예를 들어 위 선언에서 card URL은
`https://agents.example.com/a2a/planner/.well-known/agent-card.json`이고, JSON-RPC operation endpoint는
`https://agents.example.com/a2a/planner/`입니다. `base_url`을 생략하면 framework가
`A2AConfig.default_base_url.rstrip("/") + mount_path`로 유도하므로 기본 설정에서는
`http://localhost:8000/a2a/planner`가 광고됩니다. REST도 `rest_base_url`을 생략하면
`default_base_url + rest_mount_path`를 광고합니다.

```python
from starlette.applications import Starlette
from spakky.core.pod.annotations.pod import Pod


@Pod(name="asgi_host")
def asgi_host() -> Starlette:
    return Starlette()
```

gRPC 노출은 `grpc_enabled=True`인 entry를 `spakky-grpc`의 `GrpcServerSpec`에 자동 등록합니다.
따라서 애플리케이션은 `spakky-a2a`와 `spakky-grpc` plugin을 함께 로드하고
`SPAKKY_GRPC_BIND_ADDRESSES`를 설정하면 됩니다. `spakky-grpc`가 로드되지 않은 애플리케이션에서는
gRPC 선언은 no-op입니다.

애플리케이션 bootstrap 이후 `A2AAgentServerSpec.build_app_for("planner")`,
`build_rest_app_for("planner")`, `build_grpc_handler_for("planner")`는 특수 host나 테스트에서 쓰는
lower-level escape hatch입니다. 일반 애플리케이션은 `@A2ACompatible` 선언과 host Pod만 사용합니다.

## AgentCard 유도

`AgentCardFactory`는 다음 입력에서 card를 유도합니다.

- name/description: `AgentExecutionSpec.name`, `objective`, 또는 `instructions`
- streaming capability: `streaming_exposure_mode`; `NO_STREAM_UNTIL_FINAL_GUARDED`는 streaming capability 노출을 끕니다.
- tool: synthetic teammate delegation tool을 제외한 native `@agent_tool` descriptor
- delegation skill: 선언된 `AgentTeammate` entry

## 실행별 입력

Executor는 A2A inbound message의 task id를 `RunAgentInput.state_id`로, context id를 `conversation_id`로 사용합니다. A2A inbound에는 core `parent_run_id`를 채우는 별도 mapping이 없습니다. Message data part의 canonical `modelSelection`은 `RunAgentInput.model_selection`으로, `mcp`와 `metadata` object는 `RunAgentInput.metadata`로 전달됩니다.

Model-selection object에는 `modelRef` 하나만 허용합니다. 이 값은 operator가 공개한 case-sensitive opaque catalog key이며 `/`를 provider/model 구분자로 분해하지 않습니다. Profile, provider, physical model, endpoint와 credential은 A2A caller surface가 아닙니다. Executor는 모든 data part를 scan하고 legacy outer `model_selection`, canonical selector 둘 이상, `provider`, `profile`, `model`, inner `model_ref`, unknown sibling key를 발견하면 첫 값을 채택하지 않고 fail closed합니다.

```json
{
  "modelSelection": {"modelRef": "support/primary"},
  "mcp": {"servers": ["github"]},
  "metadata": {"tenant": "acme"}
}
```

Run metadata도 모든 data part를 순서대로 scan합니다. 각 `metadata` object는 기존 key에 update되고
각 explicit `mcp` object는 `metadata["mcp"]`에 저장되므로 같은 data part에서는 explicit `mcp`가
generic metadata의 동명 key보다 우선하고, 서로 다른 part 사이에서는 뒤에서 처리된 값이 앞 값을
덮어씁니다. 이 merge는 model routing authority가 아니며 endpoint/credential/physical model을 바꾸지
못합니다.

Approval resume은 data part의 `approval_id`, `decision`을 `APPROVAL_DECISION` signal로 변환합니다.

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

원격 delegation은 SDK client로 `message/send`를 보내고 remote task stream을 추적한 뒤, child task/message/artifact update를 `parent_run_id`가 설정된 Spakky protocol-neutral event stream으로 되돌립니다. 이는 parent agent 내부 attribution이며 A2A server projector가 별도 parent Task를 자동 생성하거나 모든 event에 parent id를 직렬화한다는 뜻은 아닙니다.

## Event projection

`SpakkyAgentExecutor`는 inbound task id/context id로 하나의 `TaskUpdater`를 bind한 뒤 core
`AgentEvent`를 A2A task update로 변환합니다. `RUN_STARTED`는 working transition, step/tool lifecycle은
status metadata, message/reasoning delta는 agent message, tool result와 artifact는 A2A artifact,
state snapshot/delta는 data part로 투영됩니다. `RUN_FINISHED`는 projector가 `RunOutcome`으로 반환하고
executor가 stream 종료 후 complete/failed terminal transition을 한 번 적용하며, `RUN_PAUSED`는 즉시
input-required/auth-required 상태로 변환합니다.

Bounded iterative runner의 `model-1`, `tool-1`, `model-2`, … step은 각각 A2A working status metadata로
표면화됩니다. Tool result artifact 뒤 다음 model step이 같은 Task/context에서 이어지고 terminal
model step 뒤 executor가 complete를 한 번만 적용합니다. Candidate batch가 invalid·limit 초과·approval
rejected이면 tool prefix artifact를 만들지 않고 failed outcome으로 닫습니다. Tool은 승인 뒤 순서대로
실행되므로 앞 tool의 외부 side effect를 뒤 tool failure 시 rollback하는 transaction 의미는 없습니다.

이 projection은 중립 event와 A2A event의 1:1 복사가 아닙니다. `AgentEventAttribution`과 arbitrary
event metadata 전체를 wire에 반복 직렬화하지 않고, 위 event별 field만 사용합니다. 예를 들어 message
id는 A2A message metadata, tool call name/id/phase는 status metadata, tool result는 artifact data part로
각기 다른 protocol 위치에 배치됩니다.

Candidate-only provider lifecycle은 core가 missing START/END를 한 번씩 합성하므로 A2A status metadata도
중복 없이 start/end/result 순서를 관찰합니다. Default USER_MESSAGE와 STEERING hook의 Progress는
`signal_progress` neutral artifact가 되어 A2A artifact로 추가됩니다. Neutral projection을 정의하지 않은
signal-hook yield는 `agent_signal_projection_unsupported`, model/tool/checkpoint/approval framework failure는
각 typed runner code를 가진 failed Task data part로 fail closed합니다.

Active deadline이 있는 in-process sync tool batch는 tool artifact나 side effect를 만들기 전에
`agent_sync_tool_timeout_unenforceable`로 실패합니다. 실제 timeout cancellation은 async tool에만 적용되며
A2A request cancellation이 이미 실행 중인 sync Python callable을 preempt한다고 주장하지 않습니다.

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

Core CANCEL signal은 어느 poll point에서든 canonical `cancelled` error shape로 `RunFinishedEvent`에 실리고
executor가 failed Task message + data part로 투영합니다. 별도의 A2A `tasks/cancel` operation은 durable
CANCEL signal을 enqueue한 뒤 caller가 기다리는 A2A Task를 즉시 canceled 상태로 갱신하는 transport
동작이므로 두 표면을 같은 terminal projection으로 혼동하지 않습니다.

Approval resume은 `approval_id`와 `decision`을 가진 inbound A2A data part로 전달됩니다. Executor는 `APPROVAL_DECISION` signal을 append하고 같은 task id로 `RunAgentInput(resume=True)`를 다시 실행합니다.

Fresh resume runner는 state checkpoint의 pending batch/history/counters를 복원하므로 최초 model step을
다시 호출하지 않습니다. `approve`는 original arguments를 dispatch하고 TOOL continuation 뒤 다음
model step으로 진행합니다. `defer`는 input-required 상태를 유지하며 `reject`/`cancel`은 tool을 실행하지
않습니다. Core runner는 `MODIFY`의 `modified_payload`를 signature에 다시 bind하는 계약을 갖지만,
현재 A2A `_InboundApproval` mapping은 `approval_id`와 `decision`만 signal에 전달하므로 argument-bearing
MODIFY payload를 이 boundary에서 지원한다고 간주해서는 안 됩니다.

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
