# Agent

> `spakky-agent`으로 LLM 실행과 도구 호출을 Spakky 애플리케이션 안에 넣는 채널입니다. Agent는 외부 런타임이 아니라 하나의 애플리케이션 컴포넌트로 다뤄집니다.

처음이라면 [AI Agent 개발](../guides/agents.md)로 시작하세요. 운영형 Agent로 확장할 때 필요한 도구·승인·durable 실행은 [AI Agent 심화](../guides/agents-advanced.md)에서 다룹니다. AG-UI·A2A stream adapter와 MCP tool adapter는 **어댑터** 항목에서 이어집니다.

## 기초

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [AI Agent 개발](../guides/agents.md) | `@Agent`·`RunAgentInput`·`AgentYield`로 Agent 만들기 |
| [CodeAssistant 에이전트 예제](../guides/agent-code-assistant.md) | 실제 Agent 흐름을 예제로 따라가기 |

## 심화

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [AI Agent 심화](../guides/agents-advanced.md) | tool catalog·approval·durable 실행·transport adapter |

## 어댑터

선언형 Agent는 여러 adapter와 함께 사용할 수 있습니다. AG-UI와 A2A는 `AgentRunner.run_events()`가 내보내는 protocol-neutral `AgentEvent` stream을 각 wire protocol event로 투영합니다. MCP는 event stream을 소비하지 않고 run마다 선택된 외부 MCP server tools를 lazy search/call 도구로 `AgentToolCatalog`에 합류시킵니다.

| 문서 | 무엇을 다루나요 |
| --- | --- |
| [AG-UI 어댑터](../guides/agent-ag-ui.md) | AG-UI 프로토콜로 Agent 실행을 UI에 스트리밍 |
| [A2A 어댑터](../guides/agent-a2a.md) | A2A(Agent-to-Agent) 프로토콜 연동 |
| [MCP 어댑터](../guides/agent-mcp.md) | 외부 MCP server tools를 Agent run에 연결 |

## API Reference

| 문서 | 무엇을 확인하나요 |
| --- | --- |
| [spakky-agent](../api/core/spakky-agent.md) | `AgentRunner`, `RunAgentInput`, `AgentEvent`, `AgentYield`, tool/repository/compaction 계약 |
| [spakky-agui](../api/plugins/spakky-agui.md) | AG-UI endpoint, projector, HITL, stdio helpers |
| [spakky-a2a](../api/plugins/spakky-a2a.md) | A2A AgentCard, server builder, executor, REST/gRPC transport, delegation |
| [spakky-mcp](../api/plugins/spakky-mcp.md) | 외부 MCP 서버 연결, runtime server resolution, lazy MCP tool search/call |
