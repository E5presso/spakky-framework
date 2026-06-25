# spakky-mcp

외부 MCP(Model Context Protocol) 서버의 도구를 발견해 Spakky Agent 도구 카탈로그에 합류시키는 MCP 클라이언트 어댑터 플러그인입니다. 외부 도구는 `@agent_tool`로 선언한 도구와 동일한 디스패치 경로로 자동 호출됩니다.

[ADR-0013](../../docs/adr/0013-declarative-agent-loop-ownership.md) §2에 따라 코어(`spakky-agent`)는 MCP 라이브러리에 의존하지 않으며, 외부 도구 정규화와 연결 수명주기는 이 어댑터가 전담합니다.

## 언제 필요한가

운영 중인 외부 MCP 서버의 도구를 에이전트가 일반 도구처럼 사용하고 싶을 때 사용합니다. 이 플러그인은 **도구 공급원**이며 모델 어댑터가 아닙니다 — 실행에는 별도의 `IAgentModel` 공급자(예: `spakky-vllm`)가 필요합니다.

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

## 사용

```python
from spakky.plugins.mcp import McpClient


async def run_with_external_tools(client: McpClient, agent: object) -> None:
    # 선언된 외부 서버에 연결하고, 외부 도구를 카탈로그에 더한 runner를 받는다.
    async with client.open_runner(agent) as runner:
        async for item in runner.run(run_input):
            ...  # 외부 도구가 native @agent_tool 도구와 같은 경로로 디스패치된다
```

모델이 보는 외부 도구 이름은 `<서버이름>__<도구이름>` 형태로 접두사가 붙어 서버 간 이름 충돌을 막습니다.

자세한 내용은 [MCP 클라이언트 어댑터 가이드](../../docs/guides/agent-mcp.md)를 참고하세요.

## License

MIT License
