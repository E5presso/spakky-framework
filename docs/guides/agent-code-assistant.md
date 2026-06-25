# Agent 만들기: CodeAssistant 심화 예제

> `spakky-agent`의 tool, approval, evidence, state/signal repository를 하나의 실행 흐름으로 연결하는 심화 예제입니다.

이 문서는 [AI Agent 개발](agents.md)과 [AI Agent 심화](agents-advanced.md)를 읽은 뒤 보는 실행 가능한 예제입니다. `core/spakky-agent/examples/code_assistant_demo.py`는 `CodeAssistant`가 생성자 주입으로 model, workspace, shell, git, state/signal/evidence repository를 받고, 외부 세계 동작을 `@agent_tool` 메서드로 노출하는 **선언형** 흐름을 보여줍니다. `CodeAssistant`에는 `execute()` 본문이 없습니다 — model 호출 → tool 호출 → 승인 → evidence → 종료 루프는 프레임워크 runner가 spec과 `@agent_tool` 카탈로그로부터 자동 제공합니다 (ADR-0013 §1). 시그널 반응이 필요한 지점은 `@on_signal` 훅으로 선언합니다.

## 무엇을 검증하나

이 예제는 다음 요소가 하나의 execution 안에서 어떻게 이어지는지 보여줍니다.

- `@Agent CodeAssistant`와 생성자 주입
- `workspace.read`, `workspace.search`, `workspace.write`
- `shell.command`
- `git.status`, `git.diff`, `git.apply`
- `IAgentModel.stream()` 기반 vLLM-compatible token/tool-call stream
- 위험한 작업 앞에서 멈추는 approval wait와 `AgentSignalKind.APPROVAL_DECISION`
- 실행 중 `AgentSignalKind.USER_MESSAGE` 소비
- append-only `AgentEvidence`
- `AgentSignalKind.CANCEL`을 통한 cancellation lifecycle
- action boundary evidence를 사용한 restart/resume 계획

운영용 영속 저장소는 예제 안에 포함하지 않습니다. 실제 운영에서는 `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`를 SQLAlchemy contribution 같은 provider plugin으로 주입해야 합니다.

## 실행 가능한 빠른 검증

이 가이드의 예제는 `core/spakky-agent` 패키지에 실제 코드와 테스트로 들어 있습니다. 문서 흐름이 코드와 맞는지 확인하려면 패키지 디렉터리에서 acceptance test를 실행합니다.

```bash
cd core/spakky-agent
uv run pytest tests/acceptance/test_code_assistant_demo_acceptance.py -q --no-cov
```

이 테스트는 scripted `IAgentModel` stream을 사용하므로 로컬 vLLM 서버가 없어도 실행됩니다.
테스트 double repository는 예제와 테스트를 위한 것이며, 운영 durable 실행에는
`spakky-sqlalchemy[agent]`가 제공하는 `spakky.contributions.spakky.agent`
contribution을 사용해야 합니다.

가장 작은 선언형 `@Agent` 형태는 다음 예시와 같습니다. 도구만 선언하고 `execute()`를 생략하면, 파일로 저장해 애플리케이션 scan 대상에 포함했을 때 `CodeAssistant`는 일반 UseCase처럼 container에서 resolve되고, runner가 표준 실행 루프를 `execute()`로 제공합니다.

```python
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    EvidenceCapture,
    IAgentModel,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)


@Agent(spec=AgentExecutionSpec(name="code_assistant", objective="inspect a workspace"))
class CodeAssistant:
    def __init__(self, model: IAgentModel, workspace: IWorkspacePort) -> None:
        self._model = model
        self._workspace = workspace

    @agent_tool(
        schema_name="workspace.read",
        description="Read a text file from the bounded workspace.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def workspace_read(self, path: str) -> WorkspaceReadResult:
        return self._workspace.read_text(path)
```

`code_assistant_demo.py`의 CodeAssistant는 이 최소 형태에 workspace/shell/git port 도구 7종, write/shell/apply 도구의 approval, evidence repository, action boundary resume, 그리고 `@on_signal(AgentSignalKind.STEERING_INSTRUCTION)` 훅을 더한 구성입니다. 각 개념의 배경은 [AI Agent 심화](agents-advanced.md)에서 먼저 확인할 수 있습니다.

## 구조

```python
from examples.code_assistant_demo import CodeAssistant
from spakky.agent import Agent

agent = Agent.get(CodeAssistant)

print(agent.spec.name)
print([descriptor.schema.name for descriptor in agent.tool_catalog.descriptors])
```

`CodeAssistant`는 model backend를 직접 고르지 않습니다. 생성자에 `IAgentModel`을 받으므로 테스트에서는 scripted model을, 로컬 smoke에서는 `plugins/spakky-vllm`의 `VllmAgentModel`을 주입할 수 있습니다. 이 의존 방향 덕분에 `spakky-agent` core는 vLLM이나 SQLAlchemy를 import하지 않습니다.

## 실행 collector

예제 파일의 `collect_stream()`은 FastAPI, WebSocket, Typer 같은 inbound adapter가 할 일을 작은 함수로 축약한 것입니다. 호출 입력은 `RunAgentInput`이며, runner-backed `execute()`를 순회해 `AgentYield` stream을 모읍니다.

```python
from examples.code_assistant_demo import collect_stream
from spakky.agent import RunAgentInput

items = await collect_stream(
    model,
    workspace,
    shell,
    git,
    states,
    signals,
    evidence,
    RunAgentInput(
        state_id="run-1",
        instruction="inspect the workspace and make a small approved edit",
    ),
)
```

반환되는 item은 `AgentYield` stream입니다. inbound adapter는 `token`, `tool`, `evidence`, `approval`, `cancel`, `final`을 transport별 이벤트로 바꾸면 됩니다. 최종 `FINAL` payload는 runner가 만드는 `AgentRunResult`(state_id, status, tool_calls, evidence_count)입니다. 별도 Agent 전용 inbound adapter package는 필요하지 않습니다.

## FastAPI WebSocket / Typer adapter 예제

`core/spakky-agent/examples/inbound_adapter_examples.py`는 기존 `spakky-fastapi`와 `spakky-typer` building block으로 같은 `CodeAssistant` stream을 노출합니다. 이 파일은 애플리케이션 wiring 예제이며 `spakky-agent-fastapi`나 `spakky-agent-typer` 패키지를 만들지 않습니다.

FastAPI 쪽은 `@ApiController`와 `@websocket`을 사용합니다. 컨트롤러는 container-aware Pod로 등록되고, connection handler 안에서 `CodeAssistant`를 `@UseCase`처럼 container에서 resolve한 뒤 `execute()`를 순회합니다.

```python
from examples.inbound_adapter_examples import CodeAssistantWebSocketController

# 앱 scan 대상 모듈에 controller를 포함합니다.
# WebSocket path: /agents/code/ws
```

각 `AgentYield`는 `{"kind": ..., "payload": ...}` JSON event로 전송됩니다. runner는 approval decision을 durable signal queue에서 non-blocking으로 확인하므로, WebSocket 예제는 첫 command payload의 `signals` 배열에 사전 수신된 user message / approval decision을 넣어 큐에 append한 뒤 stream을 시작합니다.

Typer 쪽은 `@CliController("agents")`와 `@command("code")`를 사용합니다. command handler 역시 container에서 `CodeAssistant`를 resolve하고 `execute()`를 호출합니다.

```bash
python main.py agents code --state-id run-1 --instruction "inspect and edit" --read-stdin-signal
```

`token` yield는 stdout에 즉시 이어 쓰고, `progress`, `approval`, `final` 같은 구조화 event는 줄 단위로 출력합니다. `--read-stdin-signal`을 켜면 stdin JSON line들을 실행 전에 signal queue로 append합니다. 따라서 approval을 같은 run에서 통과시키려면 해당 approval decision JSON line을 미리 제공하고, 이미 `approval` event를 받은 뒤 decision을 보낸 경우에는 같은 state_id로 resume run을 시작합니다.

## Approval과 resume

읽기 도구(`workspace.read`, `workspace.search`, `git.status`, `git.diff`)는 approval 없이 진행됩니다. 쓰기 또는 side effect 도구(`workspace.write`, `shell.command`, `git.apply`)는 `plan_agent_tool_approval()` 결과에 따라 `AgentYieldKind.APPROVAL`을 먼저 내보냅니다.

approval decision은 durable signal queue에 append되어야 합니다.

```python
from spakky.agent import AgentSignal, AgentSignalKind, ApprovalDecision

signals.append(
    AgentSignal(
        id="approval:run-1:workspace.write",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={
            "request_id": "approval:run-1:workspace.write",
            "decision": ApprovalDecision.APPROVE.value,
        },
    )
)
```

restart 후에는 저장된 `AgentState`, pending `AgentSignal`, append-only `AgentEvidence`를 사용해 `plan_agent_resume()`이 다음 action을 결정합니다. 완료된 boundary는 `skip_completed`, incomplete idempotent boundary는 `retry`, 불확실하거나 approval wait 중인 boundary는 `require_hitl`로 정리됩니다.

## 실제 vLLM 연결

로컬 vLLM 서버 연결은 core demo가 아니라 `spakky-vllm` plugin이 담당합니다.

```python
from spakky.agent import IAgentModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            Plugin(name="spakky-agent"),
            Plugin(name="spakky-vllm"),
        }
    )
    .start()
)
model = app.container.get(type_=IAgentModel)
```

`spakky-vllm` 플러그인은 `VllmConfig`, `HttpxVllmChatClient`, `VllmAgentModel`을 등록하고 `IAgentModel -> VllmAgentModel` binding을 설정합니다.
이 model을 `CodeAssistant` 생성자에 주입하면 `IAgentModel.stream()`에서 vLLM OpenAI-compatible SSE가 공통 `ModelStreamEvent`로 변환되어 demo Agent에 들어옵니다.
