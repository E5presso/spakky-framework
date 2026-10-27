# 실행 중 지시 수정

> `AgentSteeringUpdate`로 진행 중인 Agent의 입력을 수정·확정·철회하고, 이전 입력에서
> 생성된 출력과 아직 실행하지 않은 도구 호출을 무효화합니다. v8.5.0에서 추가된 계약입니다.

음성 인식의 중간 결과를 최종 문장으로 교체하거나, 답변 생성 중 사용자가 조건을
수정하는 경우에 사용합니다. 같은 `state_id`의 실행을 유지하면서 새 입력으로 다음
모델 요청을 구성합니다. 도구 선언과 기본 실행은 [AI Agent 개발](agents.md), 승인과
repository 구성은 [AI Agent 심화](agents-advanced.md)를 먼저 확인하세요.

## Agent와 입력 경로 구성

Agent는 `STEERING_INSTRUCTION`을 명시적으로 받아들이고 state·signal·evidence
repository를 주입받아야 합니다. 저장소 구현은 애플리케이션이 제공합니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, AgentSignalKind, RecoveryStrategy
from spakky.agent.interfaces.model import IAgentModel
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)


@Agent(
    spec=AgentExecutionSpec(
        name="conversation_assistant",
        objective="answer the current user request",
        accepted_signals=(
            AgentSignalKind.STEERING_INSTRUCTION,
            AgentSignalKind.CANCEL,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class ConversationAssistant:
    def __init__(
        self,
        model: IAgentModel,
        states: IAgentStateRepository,
        signals: IAgentSignalRepository,
        evidence: IAgentEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence
```

입력을 수신하는 애플리케이션 경계에서 실행 중인 state의 signal queue에 추가합니다.
아래 함수의 `signals`는 위 Agent가 사용하는 것과 같은 저장소이며, `state_id`는 현재
실행의 ID입니다. 전달할 때마다 고유한 `delivery_id`를 사용합니다.

```python
from spakky.agent import AgentSignal, AgentSignalKind, AgentSteeringUpdate
from spakky.agent.interfaces.repository import IAgentSignalRepository


def append_steering(
    signals: IAgentSignalRepository,
    state_id: str,
    delivery_id: str,
    update: AgentSteeringUpdate,
) -> AgentSignal:
    return signals.append(
        AgentSignal(
            id=delivery_id,
            agent_state_id=state_id,
            kind=AgentSignalKind.STEERING_INSTRUCTION,
            payload=update.model_dump(mode="json"),
        )
    )


provisional = AgentSteeringUpdate(
    input_id="conversation-1:utterance-7",
    revision=0,
    content="회의를 내일",
    final=False,
)
finalized = AgentSteeringUpdate(
    input_id="conversation-1:utterance-7",
    revision=1,
    content="내일 회의 일정만 알려 주세요.",
    final=True,
)
withdrawal = AgentSteeringUpdate(
    input_id="conversation-1:utterance-7",
    revision=2,
    content="",
    final=True,
    withdrawn=True,
)
```

HTTP·WebSocket·음성 입력을 이 queue에 넣는 endpoint는 애플리케이션이 연결합니다.
AG-UI의 후속 `RunAgentInput`은 현재 실행의 revisioned steering signal로 자동 변환되지
않습니다. [AG-UI 어댑터](agent-ag-ui.md)는 출력 투영과 승인 재개 경계를 제공합니다.

## 입력 ID와 revision

| 필드 | 의미 |
| --- | --- |
| `input_id` | 하나의 논리 입력을 식별하는 비어 있지 않은 문자열. 대화·발화 ID 등을 조합합니다. |
| `revision` | 해당 입력의 0 이상 정수 버전. 내용을 바꾸거나 철회할 때 증가시킵니다. |
| `content` | 모델 history에 넣을 텍스트. 철회할 때도 필드는 필요합니다. |
| `final` | 입력 확정 여부. `False`인 관찰은 추론에 쓸 수 있지만 도구 실행·최종 응답을 허용하지 않습니다. |
| `withdrawn` | 기본 `False`. `True`이면 해당 입력을 history에서 제거합니다. |
| `retain` | 기본 `False`. 확정 입력의 원문을 runner checkpoint에 보존할지 결정합니다. |

`AgentSignal.id`는 전달 ID, `input_id`는 수정 대상 입력 ID입니다. 같은 `input_id`의
새 revision은 이전 model message를 교체하고 다른 입력 ID의 history는 유지합니다.
낮은 revision과 완전히 같은 revision의 재전달은 소비만 하고 다시 적용하지 않습니다.
같은 revision에 다른 내용을 보내면 `AgentDefinitionError`로 거부합니다. 계약은 strict
타입과 알려진 필드만 허용합니다.

철회해도 마지막 revision 정보는 tombstone으로 남습니다. 늦게 도착한 옛 revision이
철회한 입력을 되살릴 수 없습니다. 다시 입력하려면 더 높은 revision을 사용합니다.

## 진행 중인 모델 요청과 도구 호출

Runner는 모델 이벤트를 기다리는 중에도 queue를 확인합니다. 새 revision이 있으면
이전 모델 작업을 취소하고 cleanup이 끝날 때까지 기다린 뒤 같은 run의 다음 모델
요청을 시작합니다. Async generator stream은 닫고, custom async iterator는 취소된
`__anext__` 작업에서 자원을 해제해야 합니다. 원격 취소 확인과 cleanup 오류 전파는
`IAgentModel` adapter의 책임입니다. 로컬 task 취소만으로 원격 실행 중단을 보장하지는
않습니다.

아직 확정하지 않은 입력이 하나라도 있으면 도구 batch와 최종 응답을 보류합니다.
`final=True`인 새 revision이나 철회가 도착하면 잠정 입력으로 생성한 결과를
무효화하고 다시 판단합니다. 입력 확정을 기다리는 상태는
`Progress(current_step="steering_wait")`로 나타납니다. Provider 오류는 이 대기 규칙으로
숨기지 않고 실패로 종료합니다.

도구 경계에서 입력이 수정되면 남은 미실행 호출을 버리고, 각 호출에 대응하는 `TOOL`
history에 `{"status":"not_executed","reason":"input_revised"}`를 남깁니다. 이미 완료한
도구의 결과·call ID·승인·counter는 보존합니다. 실행 중인 도구의 효과를 소급 취소하거나
완료한 도구를 자동 replay하지 않습니다. 승인 대기 중 지시가 바뀌면 이전 pending batch를
버리므로 새 도구 호출에는 새 입력과 인자에 맞는 승인이 필요합니다.

Steering이 별도의 step/tool/queue 상한을 추가하지는 않습니다. `AgentExecutionLimits`의
모든 기본값은 `None`이고, 애플리케이션이 명시한 한도와 deadline을 계속 적용합니다.
모델 요청을 다시 시작하는 것도 같은 run의 model-step counter에 반영됩니다.

## 이전 출력 무효화와 세대 식별

새 revision을 적용하면 `run()`은 `current_step="steering"`인 `Progress`를 방출합니다.
Metadata에는 `input_revision`, `input_id`, `revision`, `final`, `withdrawn`,
`invalidate_output=True`가 들어갑니다. `revision`은 개별 입력의 버전이고,
`input_revision`은 run 안에서 새 입력 변경을 적용할 때 증가하는 전체 입력 세대입니다.

화면·음성 소비자는 이 알림을 받으면 이전 답변 후보, 화면에 표시한 옛 텍스트와 대기 중인
합성 음성을 무효화해야 합니다. 이미 재생된 음성이나 외부 효과까지 되돌리는 기능은
애플리케이션이 별도로 다룹니다.

Steering을 허용하는 Agent의 `ModelRequest.metadata`와 provider event에는 모델 요청
시점에 고정한 `input_revision`이 들어갑니다. 첫 세대는 `0`입니다. 이후 revision이
적용돼도 이미 queue에 들어간 옛 text/reasoning/tool candidate 이벤트의 세대는 바뀌지
않습니다. Provider나 tool-call metadata에 같은 key가 있어도 runner가 고정한 값이
우선하므로 늦게 도착한 이전 출력을 새 출력으로 취급하면 안 됩니다.

`run_events()`는 위 Progress를 `ArtifactEvent(name="signal_progress")`로 투영합니다.
AG-UI에서는 `CUSTOM(name="artifact")`의 `value.name="signal_progress"`로 받으며,
`value.content.metadata`에 무효화 metadata가 있습니다. 표준 AG-UI text frame에는
중립 event metadata가 복사되지 않습니다. 소비자는 순서대로 받은 `TEXT_MESSAGE_START`의
message ID를 당시 입력 세대에 연결하고, 지연된 TTS 결과에도 그 연결을 유지해야 합니다.
자세한 wire 경계는 [AG-UI 어댑터](agent-ag-ui.md)를 참고하세요.

## 저장 정책과 재시작

`retain=True`이고 `final=True`인 입력만 runner checkpoint에 원문을 남길 수 있습니다.
잠정 입력은 `retain=True`여도 원문을 남기지 않습니다. 그 외 입력은 원문을 비운
message와 revision/hash 정보로 저장됩니다.

Fresh resume에서는 원문이 없는 활성 입력이 복원될 때까지 도구와 최종 응답을
보류합니다. 입력 소유자는 재시작마다 authoritative input map을 다시 전달해야 합니다.
같은 revision의 정확히 같은 update를 보내면 원래 history 위치의 빈 내용을 복원하며
입력 세대·pending approval·call correlation을 유지합니다. 의도가 바뀌었다면 더 높은
final revision이나 철회를 보내야 합니다. `content`뿐 아니라 `final`, `retain` 등도
원래 update와 일치해야 동일 입력의 재전달로 인정됩니다.

이 경로는 legacy `@on_signal` 훅을 호출하지 않고 원문 `SIGNAL` evidence도 기록하지
않습니다. 하지만 signal repository 자체의 저장 정책과 파생 MODEL evidence, assistant
출력, 도구 인자·결과는 별도 책임입니다. `retain=False`를 전체 대화의 비영속 보장으로
해석하면 안 됩니다. 상호작용 전체가 휘발성이어야 한다면 관련 저장소도 RAM으로
구성하세요. [Agent 운영](agent-operations.md)에서 evidence 경계를 함께 확인하세요.

## 잠정 입력만으로 시작한 실행

기존 목표가 없는 음성 관찰 등으로 run을 열 때는 다음 flag를 설정합니다.

```python
from spakky.agent import RunAgentInput

run_input = RunAgentInput(
    state_id="run-1",
    conversation_id="conversation-1",
    instruction="확정된 사용자 입력을 기다립니다.",
    steering_input_required=True,
)
```

이 경우 placeholder instruction만으로 도구를 실행하거나 최종 응답을 게시하지
않습니다. 실제로 입력 ID를 하나 이상 관찰한 뒤 모든 입력이 철회되면 다음과 같이
종료합니다.

| 경계 | 결과 |
| --- | --- |
| `run()` | `AgentYieldKind.CANCEL`, `Cancel(reason="input_withdrawn")` |
| 취소 metadata | `control_outcome="input_withdrawn"`, `code="agent_input_withdrawn"` |
| `run_events()` | `RunFinishedEvent.error.code="cancelled"`와 위 취소 metadata |
| state | `AgentStatus.CANCELLED`, `AgentStateReason.INPUT_WITHDRAWN` |

이는 입력 철회에 따른 제어 결과입니다. 소비자는 성공 답변과 대기 중인 음성을
게시하지 않습니다. 표준 AG-UI `RUN_ERROR`는 중립 취소 metadata 전체를 전달하지
않으므로 상세 종료 사유가 필요한 host는 중립 event도 보존해야 합니다.

기본값 `steering_input_required=False`에서는 입력을 철회해도 원래 유효한 instruction으로
실행을 계속합니다. Resume할 때 이 flag를 바꾸면 checkpoint 계약 위반으로 거부합니다.

## 기존 시그널 훅과의 관계

`input_id`가 없는 기존 `STEERING_INSTRUCTION` payload는 `@on_signal` 계약을 유지합니다.
이 가이드의 typed payload는 runner가 revision 적용과 generation 무효화를 직접
처리하므로 별도 steering hook을 작성할 필요가 없습니다. 화자·수신 대상·동의·도구 권한은
애플리케이션이 판정합니다. Revision은 입력 세대 식별이며 사용자 권한을 대신하지 않습니다.

- [spakky-agent API Reference](../api/core/spakky-agent.md)
- [ADR-0017: iterative Agent loop](../adr/0017-bounded-iterative-agent-loop.md)
