# A2A 어댑터

선언형 Agent를 A2A(Agent-to-Agent) 프로토콜로 노출하고, 다른 A2A Agent를
teammate로 위임 호출하는 어댑터입니다. 서버와 클라이언트 모두 공식
`a2a-sdk` 타입과 transport를 사용합니다.

## 서버 노출

`spakky-a2a`는 `@Agent` 선언에서 AgentCard를 파생하고, JSON-RPC/REST/gRPC
transport를 같은 executor와 TaskStore로 연결합니다. executor는 core runner의
protocol-neutral `AgentEvent` stream을 A2A task/message/artifact update로
투영합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec
from spakky.plugins.a2a import A2AAgentServer


@A2AAgentServer(base_url="https://agents.example.com/a2a", version="1.0.0")
@Agent(spec=AgentExecutionSpec(name="assistant"))
class AssistantAgent:
    ...
```

## Teammate 위임

`AgentExecutionSpec.teammates`에 선언한 teammate는 runner가 자동으로
model-callable delegation tool로 노출합니다. tool schema 이름은
`teammate.<name>.delegate`입니다.

로컬 teammate는 parent agent에 teammate pod 인스턴스를 주입하면 in-process로
실행됩니다. child run의 neutral events는 parent stream에 합류하며
`parent_run_id`가 parent run id로 설정됩니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, AgentTeammate


@Agent(spec=AgentExecutionSpec(name="researcher"))
class ResearcherAgent:
    ...


@Agent(
    spec=AgentExecutionSpec(
        name="orchestrator",
        teammates=(AgentTeammate(name="researcher", pod=ResearcherAgent),),
    )
)
class OrchestratorAgent:
    def __init__(self, researcher: ResearcherAgent) -> None:
        self._researcher = researcher
```

원격 teammate는 AgentCard URL을 선언하고 `A2AAgentDelegate`를 parent agent에
주입합니다. delegate는 AgentCard를 fetch한 뒤 SDK client로 `message/send`를
수행하고, remote task/message/artifact stream을 neutral child events로
되돌려 parent stream에 합류시킵니다.

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
class OrchestratorAgent:
    def __init__(self, delegate: A2AAgentDelegate) -> None:
        self._delegate = delegate
```

`auth-required` 같은 remote human-input pause의 first-class 처리는 별도
흐름에서 다룹니다. 현재 delegate는 정상 완료/실패 task 추적과 stream 병합을
제공합니다.
