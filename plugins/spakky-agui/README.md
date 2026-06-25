# spakky-agui

> `spakky-agui`는 `spakky-agent`를 위한 공식 AG-UI (Agent User Interaction) protocol adapter plugin입니다.
> 선언형 `@Agent` 실행 스트림을 AG-UI 이벤트로 투영(project)하여 SSE (Server-Sent Events),
> HTTP streaming, WebSocket, CLI stdio로 노출하고, deferred-tool 방식의 HITL (Human-in-the-loop) 승인 흐름을 지원합니다.

## 언제 필요한가

애플리케이션이 선언형 `@Agent` workflow를 실행하고, 그 실행 이벤트(토큰, 도구 호출,
승인 요청, 종료)를 AG-UI 호환 프런트엔드에 실시간 스트리밍하려 할 때 사용합니다.
렌더링(프런트엔드 UI)은 본 plugin의 범위 밖입니다 — 본 plugin은 와이어 프로토콜(SSE
프레임, HTTP JSON-line chunk, WebSocket text message, 또는 stdout JSON-line payload)만
책임집니다.

## 설치

```bash
pip install spakky-agui
```

durable Agent 실행(state·signal·evidence repository)과 모델 어댑터(`IAgentModel`)는
별도 provider가 제공합니다. `spakky-agui`는 inbound SSE/HTTP streaming/WebSocket/stdio
프로토콜 어댑터만 제공합니다.

## 설정

설정은 `SPAKKY_AGUI_` 환경변수 접두사를 사용하는 `AgUiConfig`로 읽습니다.

| 설정 | 기본값 | 목적 |
|------|--------|------|
| `SPAKKY_AGUI_SSE_PATH` | `/agui` | SSE endpoint가 마운트되는 경로 |
| `SPAKKY_AGUI_WEBSOCKET_PATH` | `/agui/ws` | WebSocket endpoint가 마운트되는 경로 |
| `SPAKKY_AGUI_HTTP_STREAM_PATH` | `/agui/stream` | HTTP streaming endpoint가 마운트되는 경로 |
| `SPAKKY_AGUI_EMIT_STATE_SNAPSHOT` | `true` | 중립 `STATE_SNAPSHOT` 이벤트를 AG-UI로 투영할지 여부 |
| `SPAKKY_AGUI_MESSAGES_SNAPSHOT_ENABLED` | `false` | `RUN_FINISHED` 직전에 `MESSAGES_SNAPSHOT` 프레임을 1회 방출할지 여부 |

## 동작 구조

```
AgentRunner.run_events() → 중립 AgentEvent  (런너가 native로 방출)
중립 AgentEvent  ──(AgUiProjector)──▶  AG-UI BaseEvent
AG-UI BaseEvent  ──(EventEncoder)──▶  "data: {...}\n\n" SSE 프레임
                                      또는 "{...}\n" HTTP streaming chunk
                                      또는 WebSocket text message
                                      또는 stdout "{...}\n" stdio payload
```

- **`AgentRunner.run_events()`**: 런너가 중립 `AgentEvent` taxonomy를 native로 방출하는
  스트림입니다. 메시지/추론 delta, 도구 호출 `start`/`args-delta`/`end`/`result` 생명주기,
  run/step 경계를 각각 별개 이벤트로 내보내므로, 어댑터는 별도 재구성 없이 1:1로 투영합니다.
- **`AgUiProjector`**: 중립 이벤트의 delta를 AG-UI의 START/CONTENT/END 프레이밍으로
  투영하는 상태 기계입니다. 열린 message/reasoning/tool 프레임을 추적하고, 스트림이
  중간에 끊겨도 `finish()`가 열린 프레임을 닫아 와이어 형식을 보존합니다.
- **`AgUiRunDriver`**: `run_events()`를 projector·encoder에 연결하는 async generator입니다.
  `StreamingResponse`에 직접 전달됩니다. 승인 대기는 `RunPausedEvent`로 들어오며,
  projector가 이를 deferred-tool 승인 프레임으로 직접 투영합니다(아래 HITL 참조).

## 이벤트 매핑 (중립 → AG-UI)

| 중립 `AgentEvent` | AG-UI 이벤트 |
|------------------|-------------|
| `MESSAGE_DELTA` | `TEXT_MESSAGE_START` (id 변경 시) + `TEXT_MESSAGE_CONTENT` (빈 delta는 생략) |
| `REASONING_DELTA` | `REASONING_START` + `REASONING_MESSAGE_START` + `REASONING_MESSAGE_CONTENT` |
| `TOOL_CALL_START` | `TOOL_CALL_START` (`parentMessageId`는 열린 message로 fallback) |
| `TOOL_CALL_ARGS_DELTA` | `TOOL_CALL_ARGS` (빈 delta는 생략) |
| `TOOL_CALL_END` | `TOOL_CALL_END` |
| `TOOL_CALL_RESULT` | `TOOL_CALL_RESULT` (`content`는 result의 JSON 텍스트) |
| `RUN_STARTED` | `RUN_STARTED` (`threadId`=conversation, `runId`; `parentRunId`는 `run_events`가 parent run을 세팅하지 않아 항상 없음) |
| `RUN_PAUSED` | 열린 프레임 닫기 → 승인 pause는 `hitl_approval` deferred tool `TOOL_CALL_START`/`ARGS`/`END` |
| `RUN_FINISHED` | 열린 프레임 닫기 → `RUN_FINISHED` 또는 `RUN_ERROR` |
| `STEP_STARTED`/`STEP_FINISHED` | `STEP_STARTED`/`STEP_FINISHED` |
| `STATE_SNAPSHOT` | `STATE_SNAPSHOT` (`emit_state_snapshot=true`일 때만) |
| `STATE_DELTA` | `STATE_DELTA` (JSON Patch) |
| `ARTIFACT` | `CUSTOM` (name=`artifact`) — AG-UI에 native artifact 이벤트가 없음 |

## 사용법

`@Agent`를 선언하고, FastAPI 앱에 SSE endpoint를 마운트합니다.

```python
from fastapi import FastAPI
from ag_ui.encoder import EventEncoder
from ag_ui.core import RunAgentInput as AgUiRunAgentInput

from spakky.agent import AgentRunner, RunAgentInput
from spakky.plugins.agui import (
    AgUiProjector,
    AgUiRunDriver,
    add_agui_endpoint,
    add_agui_http_stream_endpoint,
    add_agui_websocket_endpoint,
    ingest_decision,
)

app = FastAPI()
config = application.container.get(AgUiConfig)


def run_driver_factory(
    core_input: RunAgentInput,
    ag_ui_input: AgUiRunAgentInput,
    accept: str | None,
) -> AgUiRunDriver:
    assistant = application.container.get(MyAssistant)
    runner = AgentRunner.for_agent_instance(assistant)
    if core_input.resume:
        ingest_decision(ag_ui_input, runner.signals, core_input.state_id)
    return AgUiRunDriver(
        runner=runner,
        run_input=core_input,
        agent_id="my_assistant",
        projector=AgUiProjector(config),
        encoder=EventEncoder(accept=accept),
    )


add_agui_endpoint(app, run_driver_factory=run_driver_factory, config=config)
add_agui_http_stream_endpoint(app, run_driver_factory=run_driver_factory, config=config)
add_agui_websocket_endpoint(app, run_driver_factory=run_driver_factory, config=config)
```

`POST /agui`로 AG-UI `RunAgentInput`을 보내면 `text/event-stream` 응답으로 실행
이벤트가 스트리밍됩니다. `POST /agui/stream`은 같은 AG-UI event payload를 SSE `data:`
프레이밍 없이 `application/x-ndjson` HTTP response chunks로 순차 전달합니다.
WebSocket 클라이언트는 `/agui/ws`에 연결한 뒤 같은 AG-UI
`RunAgentInput` JSON을 text/JSON message로 보내고, 실행 이벤트를 AG-UI encoded text
message로 순서대로 받습니다. 같은 연결에서 후속 `RunAgentInput`을 보내 승인 결정
(`forwardedProps.approvalDecision` 또는 deferred tool-result message)을 전달할 수 있습니다.

CLI stdio 경계는 `RunAgentInput` JSON 문서를 stdin 또는 문자열 인자로 받고 stdout에 AG-UI
event payload를 한 줄에 하나씩 출력합니다. Typer 같은 CLI plugin은 이 callable을 command로
등록하면 됩니다.

```python
from sys import stdin, stdout

from spakky.plugins.agui import AgUiStdioCommand

agui_stdio = AgUiStdioCommand(
    run_driver_factory=run_driver_factory,
    input_stream=stdin,
    output_stream=stdout,
)

# CLI command body에서:
# await agui_stdio(run_input_json=None)  # stdin 사용
```

### endpoint 와이어링이 plugin `initialize`에 없는 이유

`initialize`는 `AgUiConfig`만 등록하고 endpoint를 자동 마운트하지 않습니다.
투영기(projector)는 실행마다 상태를 가지므로(열린 message/reasoning/tool 프레임 추적)
싱글턴 Pod이 될 수 없고, 어떤 `@Agent`가 요청에 응답할지는 애플리케이션마다 다르기
때문입니다. 따라서 애플리케이션 작성자가 `run_driver_factory`를 자기 Agent에 바인딩하여
`add_agui_endpoint`를 직접 호출합니다 (pydantic-ai의 `add_*_fastapi_endpoint` 패턴과 동일).

## HITL — deferred-tool 승인 흐름

AG-UI에는 1급 승인 이벤트가 없으므로, 승인 요청은 **deferred tool call**로 표면화됩니다.
`run_events()`는 승인이 필요한 도구에서 dispatch 없이 멈출 때, 성공 `RUN_FINISHED` 대신
`RunPausedEvent(reason=APPROVAL_REQUIRED)`를 방출합니다. 이 이벤트는 승인 prompt,
approval id, tool call id, allowed decisions를 담고 있으므로 어댑터가 durable state를
재조회하지 않고 직접 표면화할 수 있습니다.

1. 런너가 승인이 필요한 도구에서 멈추면, `run_events()`는 `RunPausedEvent`를 방출합니다.
   `AgUiProjector`는 이를 `hitl_approval` 도구의 `TOOL_CALL_START`/`ARGS`/`END`
   프레임으로 투영합니다 — **결과(result) 프레임은 없습니다** (결과가 지연되었기 때문).
2. 클라이언트는 이 deferred tool을 렌더링하고 사람의 결정을 받습니다.
3. 클라이언트는 다음 `RunAgentInput`에 그 결정을 담아 다시 POST합니다 — deferred call id를
   향한 tool-result 메시지로, 또는 `forwardedProps.approvalDecision`으로.
4. `ingest_decision`이 그 결정을 디코딩하여 durable signal queue에 `APPROVAL_DECISION`
   signal로 적재하면, 런너가 `run_events()`를 다시 돌며 멈췄던 지점을 재개합니다 — APPROVE는
   도구 결과와 `RUN_FINISHED`로, REJECT는 실패 `RUN_FINISHED`로 이어집니다.

## 매핑 충실도

도구·메시지·실행 이벤트 매핑은 `run_events()`를 통해 **완전 무손실(lossless)**입니다. 런너가
메시지/추론 delta, 도구 호출 `start`/`args-delta`/`end`/`result` 생명주기, run/step 경계를
각각 별개의 중립 `AgentEvent`로 native 방출하므로, 어댑터는 거친 yield를 재구성하지 않고
1:1로 투영합니다. `run_events()`는 reasoning을 지원하지 않는 모델에서는 `REASONING_DELTA`를
생략하며(graceful degrade), 현재 모델 루프가 생성하지 않는 `STATE_SNAPSHOT`/`STATE_DELTA`/
`ARTIFACT`는 live 런에서 방출되지 않습니다. projector는 taxonomy 완전성을 위해 이들 종류도
계속 처리합니다.
