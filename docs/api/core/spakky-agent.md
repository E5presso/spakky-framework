# spakky-agent

Agentic Hexagonal Architecture core contracts입니다.

## Install

```bash
pip install spakky-agent
```

`spakky-agent` owns the public contracts: `@Agent`, `AgentExecutionSpec`,
`AgentYield`, `AgentState`, `AgentSignal`, `AgentEvidence`, `IAgentModel`,
`@agent_tool`, context/safety/recovery, and delegation types. It intentionally
does not import vLLM, SQLAlchemy, FastAPI, or Typer. Durable production execution
requires repository implementations from a provider contribution such as
`spakky-sqlalchemy[agent]`; there is no production in-memory fallback.

## Public API

::: spakky.agent
    options:
      show_root_heading: false

## Execution

::: spakky.agent.execution
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

## Evidence

::: spakky.agent.evidence
    options:
      show_root_heading: false

## Context

::: spakky.agent.context
    options:
      show_root_heading: false

## Recovery

::: spakky.agent.recovery
    options:
      show_root_heading: false

## Yield

::: spakky.agent.yield_
    options:
      show_root_heading: false

## Model Interface

::: spakky.agent.interfaces.model
    options:
      show_root_heading: false

## 에러

::: spakky.agent.error
    options:
      show_root_heading: false
