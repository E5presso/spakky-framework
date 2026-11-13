# ADR-0025: 애플리케이션 정의 Agent 이벤트

- **상태**: Accepted
- **날짜**: 2026-11-14
- **대체**: 없음

## 맥락 (Context)

`AgentRunner.run_events()`가 내보내는 `AgentEvent`는 runner가 만든 것뿐이다. AG-UI의
`CUSTOM` 이벤트는 중립 `ArtifactEvent`를 `name="artifact"`로 투영할 때만 쓰였고,
`ArtifactEvent`는 내부 signal progress에서만 만들어졌다. 그래서 도구나 그 도구가 부르는
서비스가 진행 상황·중간 결과 같은 자기 이벤트를 이름과 값으로 클라이언트에 보낼 공개
경로가 없었다.

## 결정 동인 (Decision Drivers)

- 코어는 프로토콜 중립이어야 한다([ADR-0013](0013-declarative-agent-loop-ownership.md)).
  이벤트는 중립 taxonomy에 있고 투영은 adapter가 한다.
- 도구 실행 중에 낸 이벤트는 도구가 끝나기 전에 클라이언트에 도착해야 한다.
- 이벤트를 내는 코드가 runner나 adapter 객체를 인자로 받지 않아도 되어야 한다.
- 전달할 곳이 없는 이벤트를 조용히 버리지 않는다.
- `run_events()`의 기존 동작과 task 친화적 구조(`asyncio.timeout_at` 등)를 건드리지 않는다.

## 고려한 대안 (Considered Options)

### 대안 A: 도구 반환값이나 `AgentYield`에 이벤트를 싣기

기존 경로를 재사용하지만 도구가 끝난 뒤에야 전달된다. 긴 도구 호출 중의 진행 상황을
보낼 수 없다.

### 대안 B: runner가 채널을 소유하고 `run_events()` 안에서 병합하기

Adapter가 할 일이 없지만 runner의 모든 await 지점을 큐 대기와 경합시켜야 한다.
`run_events()`의 순서와 취소 의미가 모든 소비자에게서 바뀐다.

### 대안 C: adapter가 감싸는 병합 스트림과 `ContextVar` 채널 (선택)

`run_events()`는 그대로 두고, 원하는 adapter가 바깥에서 스트림을 감싼다. 이벤트를 내는
코드는 `ContextVar`로 채널을 찾는다.

## 결정 (Decision)

1. **중립 이벤트.** `AgentEventKind.CUSTOM`과
   `CustomEvent(attribution, name, value, metadata)`를 `AgentEvent`에 추가한다. 프레임워크는
   `name`과 `value`에 의미를 부여하지 않는다. 공백 이름은 `AgentDefinitionError`다.
2. **emit.** `AgentCustomEvents.emit(name, value, *, metadata=None)`은 현재 context의 채널에
   `CustomEvent`를 넣는다. 채널이 없거나 이미 닫혔으면
   `AgentCustomEventChannelUnavailableError`를 던진다. `listening()`으로 미리 확인할 수 있다.
3. **merge.** `AgentCustomEvents.merge(events, attribution)`은 원본 스트림 전체를 pump task
   하나에서 순회하고, 원본 이벤트와 emit된 이벤트를 큐 하나로 소비자에게 넘긴다.
   - 채널은 pump task를 만들 때 넘기는 context 복사본에만 묶는다. 호출자 context는
     바뀌지 않으므로 중첩된 merge는 가장 안쪽 채널을 보고, 끝나면 바깥 채널이 그대로다.
   - Pump는 소비자가 다음 항목을 요청한 뒤에만 원본을 한 단계 진행시킨다. 원본을 직접
     순회할 때와 같은 속도다.
   - 원본 예외는 먼저 큐에 들어간 항목을 전달한 뒤 전파한다.
   - 소비자가 일찍 닫거나 취소되면 pump를 취소하고 원본을 닫은 뒤 반환한다.
   - 다른 스레드(`asyncio.to_thread`)에서 온 emit은 `call_soon_threadsafe`로 실행 루프에
     넘긴다.
4. **Adapter.** `spakky-agui`의 `AgUiRunDriver`와 `spakky-a2a`의 `SpakkyAgentExecutor`가
   `run_events()`를 `merge()`로 감싼다. AG-UI는 `CUSTOM(name, value)`로, A2A는 value를 data
   part로 담고 metadata `custom_event`에 이름을 넣은 working agent message로 투영한다.
5. **예약 이름.** AG-UI에서 `artifact`는 중립 artifact 투영의 이름으로 남긴다. 같은 이름의
   애플리케이션 이벤트는 projector가 `AgUiReservedCustomEventNameError`로 거부한다. 코어는
   특정 프로토콜의 예약 이름을 알지 않는다.
6. **열린 frame.** AG-UI projector는 `CUSTOM` 이벤트에서 열린 text/reasoning/tool frame을
   닫지 않는다. Artifact·state 이벤트와 같은 처리다.

## 결과 (Consequences)

### 긍정적

- 도구와 서비스가 인자 전달 없이 자기 이벤트를 스트림에 넣고, 같은 코드가 AG-UI와
  A2A에서 모두 동작한다.
- `run_events()`를 직접 쓰는 기존 소비자는 영향이 없다.
- 클라이언트 연결이 끊기면 실행 스트림이 garbage collection을 기다리지 않고 바로 정리된다.

### 부정적

- Adapter를 직접 만드는 쪽은 `merge()`로 감싸야 emit을 받을 수 있다. 감싸지 않은
  스트림에서 emit하면 에러다.
- 예약 이름 충돌은 emit 지점이 아니라 AG-UI projector에서 드러난다.
- emit된 이벤트의 큐에는 상한이 없다. 소비자가 느린 동안 쌓이는 양은 emit하는
  애플리케이션이 정한다.

### 중립적

- 이벤트의 attribution은 `merge()`에 넘긴 값이다. 로컬 teammate child run의 도구가 낸
  이벤트도 parent 스트림의 attribution을 가진다.
- `CustomEvent.metadata`는 중립 이벤트에만 있고 AG-UI와 A2A wire에는 싣지 않는다.
- `spakky-mcp`는 `AgentEvent` stream을 소비하지 않으므로 변경이 없다.

## 참고 자료

- [ADR-0013](0013-declarative-agent-loop-ownership.md) — 프로토콜 중립 코어와 adapter 투영
- [AI Agent 심화](../guides/agents-advanced.md#custom-events)
- [AG-UI 어댑터](../guides/agent-ag-ui.md#custom-events)
