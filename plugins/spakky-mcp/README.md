# spakky-mcp

MCP(Model Context Protocol) 양방향 어댑터 플러그인입니다. **클라이언트** 방향은 외부 MCP 서버의 도구를 발견해 Spakky Agent 도구 카탈로그에 합류시키고, **서버** 방향은 Agent의 `@agent_tool` 도구를 MCP 서버로 노출해 외부 MCP 클라이언트가 발견·호출하게 합니다. 양쪽 모두 `@agent_tool`로 선언한 도구와 동일한 디스패치 경로(`AgentToolDispatcher`)로 실행됩니다.

[ADR-0013](../../docs/adr/0013-declarative-agent-loop-ownership.md) §2에 따라 코어(`spakky-agent`)는 MCP 라이브러리에 의존하지 않으며, 외부 도구 정규화·연결 수명주기와 도구의 MCP 서버 노출은 이 어댑터가 전담합니다.

## 언제 필요한가

- **클라이언트**: 운영 중인 외부 MCP 서버의 도구를 에이전트가 일반 도구처럼 사용하고 싶을 때.
- **서버**: 에이전트의 도구를 외부 MCP 클라이언트(다른 에이전트·IDE·MCP 호스트)에 표준 프로토콜로 노출하고 싶을 때.

이 플러그인은 **도구 공급원/노출원**이며 모델 어댑터가 아닙니다 — 에이전트 실행에는 별도의 `IAgentModel` 공급자(예: `spakky-vllm`)가 필요합니다.

## 설치

```bash
uv add spakky-mcp
# 또는 에이전트 번들로
uv add "spakky[agent]"
```

## 설정

외부 서버는 `SPAKKY_MCP__` 접두사 환경변수 또는 `McpConfig`로 선언합니다.

| 환경변수 | 의미 | 기본값 |
|----------|------|--------|
| `SPAKKY_MCP__SERVERS` | 외부 MCP 서버 목록(JSON 배열) | `[]` |
| `SPAKKY_MCP__CONNECT_TIMEOUT_SECONDS` | 연결 수립 타임아웃(초) | `30.0` |

서버 항목은 `name`, `transport`(`stdio` 또는 `streamable_http`), `command`/`args`/`env`(stdio), `url`(streamable_http), `call_timeout_seconds`를 가집니다. `name`은 도구 이름 충돌을 막는 접두사로 쓰이며 `__`를 포함할 수 없습니다.

도구를 MCP 서버로 노출할 때의 식별자·전송은 `SPAKKY_MCP__TOOL_SERVER__NAME`(기본 `spakky-agent`)·`SPAKKY_MCP__TOOL_SERVER__TRANSPORT`(기본 `stdio`)로 선언합니다.

`initialize()`는 `McpConfig`, `McpClient`, `McpToolServer`를 application container에 등록합니다.

## 사용

### 클라이언트: 외부 도구 끌어오기

```python
from spakky.plugins.mcp import McpClient


async def run_with_external_tools(client: McpClient, agent: object) -> None:
    # 선언된 외부 서버에 연결하고, 외부 도구를 카탈로그에 더한 runner를 받는다.
    async with client.open_runner(agent) as runner:
        async for item in runner.run(run_input):
            ...  # 외부 도구가 native @agent_tool 도구와 같은 경로로 디스패치된다
```

모델이 보는 외부 도구 이름은 `<서버이름>__<도구이름>` 형태로 접두사가 붙어 서버 간 이름 충돌을 막습니다.

`McpClient.open_runner()`는 지정된 서버들의 transport session을 열고 `list_tools()` 결과를 `AgentToolDescriptor`로 정규화한 뒤, native catalog와 external catalog를 합친 runner를 yield합니다. 이 runner는 context manager가 살아 있는 동안만 외부 도구 callable이 유효합니다. `ExternalMcpToolDescriptor`는 MCP argument object를 그대로 keyword argument로 전달하므로 MCP schema가 `args` 또는 `kwargs`라는 필드를 선언해도 Spakky의 structured-call binding heuristic에 의해 손실되지 않습니다.

### 서버: 자신의 도구 내보내기

```python
from spakky.plugins.mcp import McpToolServer


async def expose_tools(server: McpToolServer, agent: object) -> None:
    # 에이전트의 @agent_tool 도구를 stdio MCP 서버로 노출한다.
    await server.serve_stdio(agent)
```

원격 노출에는 `McpToolServer.streamable_http_session_manager(agent)`가 돌려주는 세션 매니저를 호스트 애플리케이션 lifespan에서 구동합니다.

서버 방향은 agent의 `AgentToolCatalog`를 `mcp.types.Tool` 목록으로 변환하고, inbound `call_tool`을 `AgentToolDispatcher`로 실행합니다. 반환값은 MCP `content`와 `structuredContent`로 정규화됩니다. mapping 결과는 structured payload 그대로 노출하고, scalar 결과는 `{"result": ...}`로 감싸서 항상 JSON object structured content를 제공합니다.

자세한 내용은 [MCP 어댑터 가이드](../../docs/guides/agent-mcp.md)를 참고하세요.

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License
