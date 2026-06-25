# Agent

> `spakky-agent`으로 LLM 실행과 도구 호출을 Spakky 애플리케이션 안에 넣는 채널입니다. Agent는 외부 런타임이 아니라 하나의 애플리케이션 컴포넌트로 다뤄집니다.

처음이라면 [AI Agent 개발](../guides/agents.md)로 시작하세요. 운영형 Agent로 확장할 때 필요한 도구·승인·durable 실행은 [AI Agent 심화](../guides/agents-advanced.md)에서 다룹니다. 프로토콜별 어댑터(AG-UI·A2A·MCP)는 **프로토콜 어댑터** 항목에서 이어집니다.

## 기초

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [AI Agent 개발](../guides/agents.md) | `@Agent`·`execute()`·`AgentYield`로 Agent 만들기 |
| [CodeAssistant 에이전트 예제](../guides/agent-code-assistant.md) | 실제 Agent 흐름을 예제로 따라가기 |

## 심화

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [AI Agent 심화](../guides/agents-advanced.md) | tool catalog·approval·durable 실행·transport adapter |

## 프로토콜 어댑터

선언형 Agent는 프로토콜 중립 코어 위에 어댑터를 붙여 여러 전송 프로토콜로 노출됩니다. 각 어댑터 가이드는 후속 문서 태스크가 채웁니다.

| 문서 | 무엇을 다루나요 |
| --- | --- |
| [AG-UI 어댑터](../guides/agent-ag-ui.md) | AG-UI 프로토콜로 Agent 실행을 UI에 스트리밍 |
| [A2A 어댑터](../guides/agent-a2a.md) | A2A(Agent-to-Agent) 프로토콜 연동 |
| [MCP 어댑터](../guides/agent-mcp.md) | MCP(Model Context Protocol) 클라이언트·서버 양방향 어댑터 |
