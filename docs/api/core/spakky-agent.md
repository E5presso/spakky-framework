# spakky-agent

> `spakky-agent`는 Agent workflow를 Spakky 컴포넌트로 모델링하기 위한 계약, 도구, 상태, signal, evidence 타입을 제공합니다.

Agentic Hexagonal Architecture의 core 계약입니다.

## 설치

```bash
pip install spakky-agent
```

`spakky-agent`는 `@Agent`, `AgentExecutionSpec`, `RunAgentInput`, `AgentRunner`,
`AgentEvent`, `AgentYield`, tool dispatch, context compaction, state/signal/evidence
repository port, task store, safety/recovery/delegation 타입 같은 public contract를
소유합니다. 이 패키지는 의도적으로 LLM provider SDK, SQLAlchemy, FastAPI, Typer,
AG-UI, A2A, MCP를 import하지 않습니다. 운영에서 durable execution을 사용하려면 provider
contribution의 repository 구현이 필요하며, 운영용 in-memory fallback은 제공하지
않습니다.

## Model selection과 capability

Core의 run-scoped 선택 계약은 logical ref 하나뿐입니다.

```python
from spakky.agent import ModelSelection, RunAgentInput


run_input = RunAgentInput(
    state_id="run-42",
    instruction="요청을 분류해 주세요.",
    model_selection=ModelSelection(model_ref="support/primary"),
)
```

`ModelSelection`은 frozen dataclass이며 필수 `model_ref: str` 외에 provider, profile,
physical model, metadata field를 두지 않습니다. Blank ref는 `AgentDefinitionError`입니다.
Runner는 selection을 `ModelRequest`와 `IAgentModel.capability_for()`에 전달합니다. 고정
model adapter는 같은 capability를 반환할 수 있고, `spakky-llm` 같은 catalog-aware
adapter는 opaque ref를 operator catalog에서 해석합니다.

`ModelCapability`은 reasoning, context window, token counting, input/output
`ModelModality`, tools, structured output 지원 여부를 표현합니다. 기본값은 text input과
text output만 지원하고 나머지 optional capability는 꺼진 상태입니다. Logical route
구성과 protocol별 wire shape는 [LLM 모델 라우팅](../../guides/llm-routing.md)을
확인하세요.

## Public API

::: spakky.agent
    options:
      show_root_heading: false

## 실행

::: spakky.agent.execution
    options:
      show_root_heading: false

::: spakky.agent.inbound
    options:
      show_root_heading: false

::: spakky.agent.runner
    options:
      show_root_heading: false

::: spakky.agent.runner_factory
    options:
      show_root_heading: false

## Event

::: spakky.agent.event
    options:
      show_root_heading: false

## Dispatcher

::: spakky.agent.dispatcher
    options:
      show_root_heading: false

## State

::: spakky.agent.state
    options:
      show_root_heading: false

## Signal

::: spakky.agent.signal
    options:
      show_root_heading: false

::: spakky.agent.signal_consumption
    options:
      show_root_heading: false

## Evidence

::: spakky.agent.evidence
    options:
      show_root_heading: false

## Context

::: spakky.agent.context
    options:
      show_root_heading: false

## Compaction

::: spakky.agent.compaction
    options:
      show_root_heading: false

## Recovery

::: spakky.agent.recovery
    options:
      show_root_heading: false

## Approval

::: spakky.agent.approval
    options:
      show_root_heading: false

## Cancellation

::: spakky.agent.cancellation
    options:
      show_root_heading: false

## Delegation

::: spakky.agent.delegation
    options:
      show_root_heading: false

## Safety

::: spakky.agent.safety
    options:
      show_root_heading: false

## Tooling

::: spakky.agent.tooling
    options:
      show_root_heading: false

## Signal Hooks

::: spakky.agent.hooks
    options:
      show_root_heading: false

## Yield

::: spakky.agent.yield_
    options:
      show_root_heading: false

## Model Interface

::: spakky.agent.interfaces
    options:
      show_root_heading: false

::: spakky.agent.interfaces.model
    options:
      show_root_heading: false

::: spakky.agent.interfaces.repository
    options:
      show_root_heading: false

::: spakky.agent.interfaces.task_store
    options:
      show_root_heading: false

## Types

::: spakky.agent.types
    options:
      show_root_heading: false

## Plugin

::: spakky.agent.main
    options:
      show_root_heading: false

::: spakky.agent.post_processor
    options:
      show_root_heading: false

## 에러

::: spakky.agent.error
    options:
      show_root_heading: false
