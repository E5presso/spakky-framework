# MCP 어댑터 (클라이언트·서버)

> MCP(Model Context Protocol) 양방향 어댑터 가이드입니다. **클라이언트** 방향은 외부 MCP 서버의 도구를 선언형 Agent의 도구 카탈로그에 합류시키고, **서버** 방향은 Agent의 `@agent_tool` 도구를 MCP 서버로 노출해 외부 MCP 클라이언트가 발견·호출하게 합니다.

`spakky-mcp` 플러그인은 [ADR-0013](../adr/0013-declarative-agent-loop-ownership.md) §2의 결정에 따라 프로토콜 중립 코어(`spakky-agent`) 밖에 위치하는 독립 어댑터입니다. 코어는 MCP 라이브러리에 의존하지 않으며, 외부 도구 정규화·연결 수명주기와 도구의 MCP 서버 노출은 이 플러그인이 전담합니다.

> 아래 "클라이언트" 절은 외부 도구를 끌어오는 방향이고, "서버" 절은 자신의 도구를 내보내는 방향입니다.

## 클라이언트: 외부 도구 끌어오기

## 언제 쓰는가

이미 운영 중인 외부 MCP 서버(파일 시스템, 검색, 사내 도구 서버 등)의 도구를 에이전트가 일반 도구처럼 사용하고 싶을 때 씁니다. 외부 서버를 선언하면 그 도구들이 모델에게 노출되고, 모델이 호출하면 프레임워크 실행 루프가 외부 서버로 디스패치합니다.

이 플러그인은 **도구 공급원**일 뿐 모델 어댑터가 아닙니다. 실행에는 별도의 `IAgentModel` 공급자(예: `spakky-vllm`)가 필요합니다.

## 설치

```bash
pip install spakky-mcp
# 또는 에이전트 번들로
pip install "spakky[agent]"
```

plugin 초기화는 `McpConfig`, `McpClient`, `McpToolServer`를 등록합니다. 외부 도구를 끌어올 때는 `McpClient`, 자신의 도구를 내보낼 때는 `McpToolServer` 또는 module-level server helper를 사용합니다.

## 외부 서버 선언

외부 서버는 `SPAKKY_MCP__` 접두사 환경변수 또는 `McpConfig`로 선언합니다. `transport`는 `stdio`(하위 프로세스로 서버 구동)와 `streamable_http`(원격 HTTP 서버)를 지원합니다.

```bash
# stdio 서버 1개를 JSON 배열로 선언
export SPAKKY_MCP__SERVERS='[{"name": "weather", "command": "weather-mcp-server"}]'
```

| 환경변수 | 의미 | 기본값 |
|----------|------|--------|
| `SPAKKY_MCP__SERVERS` | 외부 MCP 서버 목록(JSON 배열) | `[]` |
| `SPAKKY_MCP__CONNECT_TIMEOUT_SECONDS` | 연결 수립 타임아웃(초) | `30.0` |

서버 항목 필드:

| 필드 | 의미 |
|------|------|
| `name` | 서버 이름. 도구 이름 충돌을 막는 접두사로 쓰이며 `__`를 포함할 수 없습니다. |
| `transport` | `stdio`(기본) 또는 `streamable_http` |
| `command`, `args`, `env` | `stdio` 전송에서 서버를 구동할 명령·인자·환경변수 |
| `url` | `streamable_http` 전송에서 서버의 http(s) 엔드포인트 |
| `call_timeout_seconds` | 도구 호출 타임아웃(초). 기본 `60.0` |

## 도구 이름 접두사

여러 서버가 같은 이름의 도구를 노출해도 충돌하지 않도록, 모델이 보는 도구 이름은 `<서버이름>__<도구이름>` 형태로 접두사가 붙습니다. 예를 들어 `weather` 서버의 `forecast` 도구는 카탈로그에 `weather__forecast`로 등록됩니다.

## 에이전트에 합류시키기

`McpClient.open_runner`는 선언한 외부 서버에 연결해 도구를 발견하고, 에이전트의 기존 도구 카탈로그에 외부 도구를 더한 `AgentRunner`를 돌려줍니다. 외부 서버 세션은 `async with` 블록 동안 유지되며 블록을 벗어나면 정리됩니다.

```python
from spakky.plugins.mcp import McpClient


async def run_with_external_tools(client: McpClient, agent: WeatherAgent) -> None:
    async with client.open_runner(agent) as runner:
        async for item in runner.run(run_input):
            ...  # 외부 도구가 native @agent_tool 도구와 같은 경로로 디스패치된다
```

`server_names`를 지정하면 선언된 서버 중 일부만 연결합니다(`open_runner(agent, server_names=["weather"])`). 인자를 생략하면 선언된 모든 서버를 연결합니다.

## 동작 원리: 소유자 없는(owner-less) 도구

발견된 외부 도구는 소유 클래스가 없는 `AgentToolDescriptor`로 정규화됩니다. 이 디스크립터의 호출 대상은 첫 인자가 `self`/`cls`가 아닌 비동기 콜러블이라, `AgentToolDispatcher`가 인스턴스를 바인딩하지 않고 모델이 전달한 인자만 그대로 외부 서버 `call_tool`로 넘깁니다. 그 결과 외부 도구는 `@agent_tool` 메서드와 **단일 디스패치 경로**를 공유합니다.

외부 도구는 네트워크 외부 부수효과(external side-effect)로 표시되어, 프레임워크의 HITL(Human-In-The-Loop) 승인 판정에서 승인 후보로 분류됩니다.

## 안전 경계

- 외부 도구 결과는 구조화 콘텐츠(`structuredContent`)가 있으면 그대로, 없으면 텍스트 콘텐츠를 모아 JSON 값으로 정규화합니다.
- 서버가 오류 결과(`isError`)를 반환하거나 연결·디스커버리·호출이 실패하면 `McpTransportError`·`McpToolDiscoveryError`·`McpToolInvocationError` 등 타입화된 오류로 표면화됩니다.
- 외부 도구 이름이 기존 카탈로그 도구와 충돌하면 `McpCatalogMergeError`로 거부됩니다.

## 서버: 자신의 도구 내보내기

반대 방향으로, Agent가 선언한 `@agent_tool` 도구를 MCP 서버로 노출하면 외부 MCP 클라이언트가 표준 MCP 프로토콜로 그 도구들을 발견·호출할 수 있습니다. 노출된 각 도구는 모델이 보는 것과 같은 디스패치 경로(`AgentToolDispatcher`)로 실행되므로, 원격 클라이언트의 호출은 로컬 모델의 도구 호출과 동일하게 동작합니다.

### 서버 만들기

`build_agent_tool_server(agent_instance, server_name)`는 한 에이전트 인스턴스의 도구 카탈로그를 노출하는 MCP `Server`를 만듭니다. `list_tools` 요청에는 각 카탈로그 디스크립터를 `mcp.types.Tool`(모델용 이름·설명·입력 JSON Schema)로 변환해 응답하고, `call_tool` 요청은 디스패처로 위임합니다.

```python
from spakky.plugins.mcp import build_agent_tool_server, serve_stdio


async def expose_over_stdio(agent: WeatherAgent) -> None:
    server = build_agent_tool_server(agent, "spakky-agent")
    await serve_stdio(server)  # stdio 전송으로 클라이언트가 연결을 닫을 때까지 서빙
```

`McpToolServer` Pod를 쓰면 설정(`McpConfig.tool_server`)에 선언한 서버 이름·전송으로 같은 작업을 수행합니다.

```python
from spakky.plugins.mcp import McpToolServer


async def expose(server: McpToolServer, agent: WeatherAgent) -> None:
    await server.serve_stdio(agent)
```

### 전송 선택

| 전송 | 진입점 | 용도 |
|------|--------|------|
| `stdio` | `serve_stdio(server)` / `McpToolServer.serve_stdio(agent)` | 클라이언트가 하위 프로세스로 서버를 구동 |
| `streamable_http` | `streamable_http_session_manager(server)` / `McpToolServer.streamable_http_session_manager(agent)` | 원격 HTTP 노출 — 반환된 세션 매니저를 호스트 애플리케이션의 lifespan에서 구동하고 인바운드 요청을 `handle_request`로 라우팅 |

`streamable_http` 세션 매니저는 자신의 `run()` 컨텍스트 동안 단일 task group을 소유하며 컨텍스트를 벗어나면 재사용할 수 없습니다 — 호스트 애플리케이션 lifespan에서 1회 구동합니다.

### 서버 노출 설정

| 환경변수 | 의미 | 기본값 |
|----------|------|--------|
| `SPAKKY_MCP__TOOL_SERVER__NAME` | MCP 핸드셰이크에서 광고할 서버 이름 | `spakky-agent` |
| `SPAKKY_MCP__TOOL_SERVER__TRANSPORT` | `stdio`(기본) 또는 `streamable_http` | `stdio` |

### 결과 변환

도구 디스패치 결과는 MCP의 `content`(사람이 읽는 텍스트)와 `structuredContent`(기계가 읽는 JSON)로 변환됩니다. 매핑(`dict`) 결과는 그대로 구조화 콘텐츠가 되고, 그 외 값은 `{"result": ...}` 형태로 감싸집니다 — 이는 클라이언트 방향의 결과 정규화(`normalize_call_result`)가 읽어 들이는 형태와 대칭입니다. 디스패치가 실패하면 `McpToolExposureError`로 표면화되어 SDK가 원격 클라이언트에 도구 오류로 보고합니다.

## 함께 보기

- [AI Agent 개발](agents.md)
- [AI Agent 심화](agents-advanced.md)
- [spakky-mcp API Reference](../api/plugins/spakky-mcp.md)
- [spakky-agent API Reference](../api/core/spakky-agent.md)
- [ADR-0013: 선언형 Agent](../adr/0013-declarative-agent-loop-ownership.md)
