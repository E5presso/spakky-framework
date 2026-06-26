# spakky-mcp

> `spakky-mcp`는 외부 MCP server tools를 Spakky Agent run에 연결하는 단방향 adapter입니다.

`McpClient`가 `IAgentRunnerFactory` 구현체로 외부 서버 연결 수명주기를 소유합니다. `McpRuntimeServerResolver`는 configured server 이름과 run-time inline server 선언을 해석하고, descriptor 계층은 발견된 MCP tools를 lazy search/call meta-tools 뒤에 보관합니다.

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

## Runtime Resolution

::: spakky.plugins.mcp.runtime
    options:
      show_root_heading: false

## Descriptor

`descriptor` 모듈은 `McpClient`가 발견한 외부 MCP tools를 lazy `mcp_search_tools` / `mcp_call_tool` 표면 뒤에 보관하기 위한 내부 정규화 계층입니다. 애플리케이션 코드는 일반적으로 `McpClient`, `McpConfig`, `IMcpRuntimeServerResolver`만 사용합니다. `mcp_call_tool` approval request는 meta-tool이 아니라 선택된 외부 MCP tool 이름과 arguments를 노출합니다.

::: spakky.plugins.mcp.descriptor
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
