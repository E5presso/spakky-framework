# CodeAssistant building-block demo

`core/spakky-agent/examples/code_assistant_demo.py`는 ADR-0009의 Claude Code-like 흐름을 제품 앱이 아니라 프레임워크 조합 예제로 보여줍니다. 핵심은 `@Agent` business component가 constructor DI로 model, workspace, shell, git, state/signal/evidence repository를 받고, 외부 세계 동작은 `@agent_tool` method로 노출한다는 점입니다.

## 무엇을 검증하나

이 demo는 다음 building block이 한 execution 안에서 연결되는지 보여줍니다.

- `@Agent CodeAssistant`와 constructor DI
- `workspace.read`, `workspace.search`, `workspace.write`
- `shell.command`
- `git.status`, `git.diff`, `git.apply`
- `IAgentModel.stream()` 기반 vLLM-compatible token/tool-call stream
- risk-boundary approval wait와 `AgentSignalKind.APPROVAL_DECISION`
- 실행 중 `AgentSignalKind.USER_MESSAGE` 소비
- append-only `AgentEvidence`
- `AgentSignalKind.CANCEL`을 통한 cancellation lifecycle
- action-boundary evidence 기반 restart/resume 계획

운영용 persistence나 production in-memory fallback은 포함하지 않습니다. 실제 운영에서는 `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`를 SQLAlchemy contribution 같은 provider plugin으로 주입해야 합니다.

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

반환되는 item은 `AgentYield` stream입니다. inbound adapter는 `token`, `tool`, `evidence`, `approval`, `cancel`, `final`을 transport별 이벤트로 바꾸면 됩니다. 별도 agent-specific inbound adapter package는 필요하지 않습니다.

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

restart 후에는 저장된 `AgentState`, pending `AgentSignal`, append-only `AgentEvidence`를 사용해 `plan_agent_resume()`이 다음 action을 결정합니다. 완료된 boundary는 `skip_completed`, incomplete idempotent boundary는 `retry`, 불확실하거나 approval wait 중인 boundary는 `require_hitl`로 materialize됩니다.

## 실제 vLLM 연결

로컬 vLLM 서버 연결은 core demo가 아니라 `spakky-vllm` plugin이 담당합니다.

```python
from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.model import VllmAgentModel

model = VllmAgentModel(VllmConfig(), HttpxVllmChatClient())
```

이 model을 `CodeAssistant` 생성자에 주입하면 `IAgentModel.stream()`에서 vLLM OpenAI-compatible SSE가 provider-neutral `ModelStreamEvent`로 변환되어 demo agent에 들어옵니다.
