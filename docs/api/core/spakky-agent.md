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

## Bounded iterative runner

`execute()`를 생략한 `@Agent`에는 framework-owned iterative loop가 합성됩니다. 각 model
step은 terminal response와 whole tool batch를 모은 뒤 catalog/ID/signature/authority를
전부 검증합니다. Gate가 열리면 tool을 순차 dispatch하고 assistant tool-call message와
`TOOL` result message를 history에 추가해 다음 model step을 호출합니다. Tool call이 없는
valid terminal step에서 `FINAL` 또는 `RUN_FINISHED`를 정확히 한 번 방출합니다.

`AgentExecutionSpec.limits`의 타입은 `AgentExecutionLimits`이며 default는 다음과 같습니다.

| 필드 | 기본값 | 집행 시점 |
| --- | --- | --- |
| `max_steps` | `8` | 다음 model request 직전 |
| `max_tool_calls` | `32` | candidate batch 전체 dispatch 직전 |
| `max_tokens` | `None` | 각 terminal provider usage 누적 직후 |
| `timeout_seconds` | `None` | model과 async tool await의 invocation deadline |

`AgentExecutionSpec.timeout_seconds` alias는 없습니다. `max_tokens`가 설정됐지만 provider가
`ModelUsage.total_tokens`를 주지 않으면 `agent_usage_unavailable`로 fail closed합니다.
Streaming path와 `NO_STREAM_UNTIL_FINAL_GUARDED`의 `complete()` path는 같은 batch,
authority, history, limit, terminal uniqueness 의미를 사용합니다.

Deadline이 있는 batch에 in-process sync tool이 포함되면 timeout을 실행 중 강제할 수
없으므로 runner가 전체 batch를 호출 전에 `agent_sync_tool_timeout_unenforceable`로
거부합니다. Async tool만 actual timeout 경계 안에서 실행됩니다.

Approval checkpoint는 call ID만 저장하지 않고
`approval:{state_id}:{call_id}:{digest}` fingerprint를 저장합니다. `digest`는 canonical
JSON argument에 대한 full SHA-256이므로 persisted argument가 바뀌면 기존 승인을
재사용하지 않습니다. `MODIFY` 성공 시 pending call과 assistant `tool_calls` history 모두
최종 approved arguments로 교체됩니다.

Candidate-only provider stream은 `run_events()`가 missing tool START/END frame만 합성합니다.
Signal hook의 `Progress` yield는 event surface에서 `ArtifactEvent(name="signal_progress")`가
되며 다른 yield shape는 `agent_signal_projection_unsupported`로 fail closed합니다.

Compaction은 assistant tool-call과 모든 correlated `TOOL` results를 하나의 group으로
보존합니다. Runner는 입력과 각 custom strategy 출력 직후 correlation을 검증하며 orphan
또는 incomplete group은 provider 호출 전에 `agent_model_execution_failed`로 종료합니다.

Protocol-neutral event step은 `model-N`, 실제 tool dispatch는 `tool-N`입니다. Message/reasoning ID와
missing tool-call ID도 model step과 batch index를 포함합니다. Step metadata와 durable
model evidence는 누적 model/tool/token counter, provider usage, 제공된 actual route
`model_ref`/`profile`/`provider`/`model`을 보존합니다. Protocol projector가 이 metadata
전체를 wire에 보존한다는 의미는 아닙니다.

Token budget failure도 현재 step의 route/usage/counters를 terminal metadata에 보존하고,
durable path에서는 동일 snapshot과 typed error를 model-decision evidence로 남깁니다.

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
