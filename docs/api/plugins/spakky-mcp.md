# spakky-mcp

> `spakky-mcp`는 외부 MCP server tool을 `AgentToolCatalog`에 병합하고, 반대로 `@agent_tool` 카탈로그를 MCP server로 노출하는 양방향 어댑터입니다.

client 방향은 외부 서버 연결 수명주기를 `McpClient.open_runner()`가 소유하고, server 방향은 `McpToolServer` 또는 `build_agent_tool_server()`가 한 agent instance의 tool catalog를 MCP `Server`로 변환합니다.

## Public API

::: spakky.plugins.mcp
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.mcp.config
    options:
      show_root_heading: false

::: spakky.plugins.mcp.constants
    options:
      show_root_heading: false

## Client

::: spakky.plugins.mcp.client
    options:
      show_root_heading: false

## Descriptor

::: spakky.plugins.mcp.descriptor
    options:
      show_root_heading: false

## Server

::: spakky.plugins.mcp.server
    options:
      show_root_heading: false

## Plugin

::: spakky.plugins.mcp.main
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.mcp.error
    options:
      show_root_heading: false
