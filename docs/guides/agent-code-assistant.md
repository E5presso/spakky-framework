# Agent 만들기: CodeAssistant 심화 예제

> `spakky-agent`의 tool, approval, evidence, state/signal repository를 하나의 실행 흐름으로 연결하는 심화 예제입니다.

이 문서는 [AI Agent 개발](agents.md)과 [AI Agent 심화](agents-advanced.md)를 읽은 뒤 보는 실행 가능한 예제입니다. `core/spakky-agent/examples/code_assistant_demo.py`는 `CodeAssistant`가 생성자 주입으로 model, workspace, shell, git, state/signal/evidence repository를 받고, 외부 세계 동작을 `@agent_tool` 메서드로 노출하는 흐름을 보여줍니다.

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

가장 작은 실행 가능한 `@Agent` 형태는 다음 예시와 같습니다. 파일로 저장해 애플리케이션 scan 대상에 포함하면 `CodeAssistant`는 일반 UseCase처럼 container에서 resolve됩니다.

```python
from collections.abc import AsyncGenerator

from spakky.agent import Agent, AgentExecutionSpec, AgentYield, AgentYieldKind, Final
from spakky.core.pod.annotations.pod import Pod


@Pod()
class AnswerTools:
    def answer(self, command: str) -> str:
        return f"handled:{command}"


@Agent(spec=AgentExecutionSpec(name="code_assistant", objective="handle commands"))
class CodeAssistant:
    def __init__(self, tools: AnswerTools) -> None:
        self._tools = tools

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=self._tools.answer(command), metadata={}),
        )
```

CodeAssistant 예제는 이 최소 형태에 model stream, workspace/shell/git port, approval signal, evidence repository, action boundary resume를 더한 구성입니다. 각 개념의 배경은 [AI Agent 심화](agents-advanced.md)에서 먼저 확인할 수 있습니다.

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

예제 파일의 `collect_stream()`은 FastAPI, WebSocket, Typer 같은 inbound adapter가 할 일을 작은 함수로 축약한 것입니다.

```python
from examples.code_assistant_demo import CodeAssistantCommand, collect_stream

items = await collect_stream(
    model,
    workspace,
    shell,
    git,
    states,
    signals,
    evidence,
    CodeAssistantCommand(
        state_id="run-1",
        instruction="inspect the workspace and make a small approved edit",
    ),
)
```

반환되는 item은 `AgentYield` stream입니다. inbound adapter는 `token`, `tool`, `evidence`, `approval`, `cancel`, `final`을 transport별 이벤트로 바꾸면 됩니다. 별도 Agent 전용 inbound adapter package는 필요하지 않습니다.

## FastAPI WebSocket / Typer adapter 예제

`core/spakky-agent/examples/inbound_adapter_examples.py`는 기존 `spakky-fastapi`와 `spakky-typer` building block으로 같은 `CodeAssistant` stream을 노출합니다. 이 파일은 애플리케이션 wiring 예제이며 `spakky-agent-fastapi`나 `spakky-agent-typer` 패키지를 만들지 않습니다.

FastAPI 쪽은 `@ApiController`와 `@websocket`을 사용합니다. 컨트롤러는 container-aware Pod로 등록되고, connection handler 안에서 `CodeAssistant`를 `@UseCase`처럼 container에서 resolve한 뒤 `execute()`를 순회합니다.

```python
from examples.inbound_adapter_examples import CodeAssistantWebSocketController

# 앱 scan 대상 모듈에 controller를 포함합니다.
# WebSocket path: /agents/code/ws
```

각 `AgentYield`는 `{"kind": ..., "payload": ...}` JSON event로 전송됩니다. `approval` event를 보낸 뒤 client가 `{"kind": "approval_decision", "decision": "approve"}` 같은 payload를 보내면 adapter가 `IAgentSignalRepository.append()`로 decision signal을 추가하고 generator를 계속 소비합니다.

Typer 쪽은 `@CliController("agents")`와 `@command("code")`를 사용합니다. command handler 역시 container에서 `CodeAssistant`를 resolve하고 `execute()`를 호출합니다.

```bash
python main.py agents code --state-id run-1 --instruction "inspect and edit" --read-stdin-signal
```

`token` yield는 stdout에 즉시 이어 쓰고, `progress`, `approval`, `final` 같은 구조화 event는 줄 단위로 출력합니다. `--read-stdin-signal`을 켜면 첫 stdin JSON line을 user message signal로 append하고, approval 대기 시 다음 stdin JSON line을 approval decision signal로 append합니다.

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
from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.model import VllmAgentModel

model = VllmAgentModel(VllmConfig(), HttpxVllmChatClient())
```

이 model을 `CodeAssistant` 생성자에 주입하면 `IAgentModel.stream()`에서 vLLM OpenAI-compatible SSE가 공통 `ModelStreamEvent`로 변환되어 demo Agent에 들어옵니다.
