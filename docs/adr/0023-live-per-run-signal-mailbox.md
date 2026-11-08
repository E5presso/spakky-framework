# ADR-0023: 실행별 신호 메일박스와 control·steering 두 차선

- **상태**: Accepted
- **날짜**: 2026-11-08
- **대체**: [ADR-0017](0017-bounded-iterative-agent-loop.md) §10의 "blocked model await 중 pending repository polling" 부분

## 맥락 (Context)

v8.5.0의 revisioned steering(`f9ed9829`)은 모델 스트림과 도구 대기 중에
`STEERING_POLL_SECONDS = 0.01` 간격으로 `IAgentSignalRepository.list_pending()`을
불렀다. 한 대기 지점에서 steering 적용과 취소 확인이 각각 조회하므로 작업 하나당
초당 약 200회의 조회가 생겼다. SQLAlchemy 구현의 `list_pending()`은 동기 세션
SELECT라 이벤트 루프를 멈춘다. Amber 운영 프로파일에서 `list_pending`은 1분에
8,524회, 60초 중 25.6초를 차지했고, 작업 두 개만 겹쳐도 루프가 포화되어 모델
호출이 수 초씩 늦었다. 신호 `append()`는 행을 `flush`할 뿐 아무도 깨우지 않았다.

## 결정 동인 (Decision Drivers)

- 신호가 없는 동안 실행은 원장(DB)을 0회 조회해야 한다.
- 신호는 생산자 트랜잭션이 커밋된 뒤에만 실행에 보여야 한다(openai/codex#40805).
- 취소·긴급 입력은 진행 중인 모델 호출을 즉시 끊어야 하고, 일반 조향은 응답을
  끊지 않고 안전 지점에 모아서 넣어야 한다(Codex `input_queue`).
- 중단 시 대기 중 조향을 버리면 안 된다(botiverse/oar#236).
- 끝난 실행이나 지난 판본 신호는 실행 식별과 같은 임계 구역에서 거절한다
  (openai/codex#18392).
- 기존 신호 kind, `list_pending`·`mark_consumed` 의미, 조향 판본 규칙을 유지한다.

## 고려한 대안 (Considered Options)

### 대안 A: 폴링 간격만 늘리거나 비동기 세션으로 바꾸기

조회 비용은 줄지만 지연과 조회 횟수의 맞교환일 뿐이다. 신호가 없어도 조회가
계속되고, 커밋 전 행이 보이는 문제와 깨움 부재도 그대로다.

### 대안 B: `append()`에서 바로 알리기

조회는 사라지지만 롤백된 트랜잭션의 신호로 실행을 깨운다. 소비자가 그 신호를
원장에서 찾지 못하거나, 커밋 전에 수신을 확인하게 된다.

### 대안 C: 원장과 실시간 경로를 분리한 실행별 메일박스 (선택)

Temporal의 "시작 시 1회 재생 + 이후 이벤트 수신", Codex의 `input_queue`와
`drain_mailbox_input_items`, LangGraph·Hermes의 interrupt/steer 구분을 따른다.

## 결정 (Decision)

1. **원장과 실시간 경로 분리.** `agent_signal` 행은 원장(아웃박스)으로만 쓴다.
   실시간 전달은 `IAgentSignalPublisher.publish(signal)`와
   `IAgentSignalSubscriber.subscribe(state_id) -> AgentRunMailbox` 두 포트로 한다.
   기본 구현 `InProcessAgentSignalMailbox`는 두 포트를 함께 구현하는 `@Pod`이고
   `spakky-agent`의 `initialize()`가 등록한다. 다른 스레드·루프의 생산자는
   `call_soon_threadsafe`로 실행 루프에 넘기고, 같은 루프의 생산자(예: 도구)는
   즉시 받아 다음 경계에서 보이게 한다. PostgreSQL `NOTIFY`나 Kafka 같은
   프로세스 간 전송은 같은 publisher 포트를 구현해 꽂을 수 있다(이번 범위 밖).
2. **커밋 후 게시.** `SqlAlchemyAgentSignalRepository.append()`는 행을 쓴 트랜잭션
   (또는 savepoint)에 묶어 staging한다. 주입된 publisher가 있으면 가장 바깥
   트랜잭션이 커밋될 때만 게시한다. 해제된 savepoint의 행은 바깥 커밋을 기다리고,
   savepoint 롤백은 그 안에서 쓴 행만 버리며, 바깥 롤백이나 `close()`는 남은 행을
   모두 버린다.
3. **두 차선.** `AgentSignal.lane`은 `CANCEL` kind이거나
   `priority=AgentSignalPriority.URGENT`이면 `CONTROL`, 나머지는 `STEERING`이다.
   - `CONTROL`: runner는 모델 작업 태스크와 메일박스 control 대기를
     `asyncio.wait(FIRST_COMPLETED)`로 함께 기다리다 즉시 `cancel()`한다. 공급자
     cleanup을 기다린 뒤 같은 run의 다음 단계로 넘어간다. 긴급 조향을 적용할 때는
     그보다 먼저 대기 중이던 조향도 도착 순서대로 함께 적용한다.
   - `STEERING`: 메일박스에 쌓아 두고 모델 응답 종료·도구 경계 같은 안전 지점에서
     일괄 주입한다. 진행 중 응답은 끝까지 받는다.
   - `priority`는 실시간 전달 힌트이며 원장 행에 저장하지 않는다. 재생되는 신호는
     실행 시작의 첫 안전 지점에서 적용되므로 끊을 진행 작업이 없다.
4. **폴링 제거.** 실행은 메일박스를 먼저 구독한 뒤 미소비 원장을 1회 재생한다.
   그 사이 커밋된 신호는 양쪽에 보이며 id로 중복 제거한다. 이후 모든 경계 확인은
   실행 내 inbox의 메모리 조회이고, 입력 대기는 메일박스 도착을 기다린다.
5. **계약.**
   - `mark_consumed`는 적용한 뒤에만 부른다.
   - 취소가 대기 중이면 어느 안전 지점에서도 조향을 소비하지 않아, 대기 중 조향은
     원장에 미소비로 남는다. 긴급 조향으로 중단하면 대기 조향도 재시작 단계에 주입된다.
   - 메일박스는 루프 위에서 `closed`·`state_id`를 확인한 뒤에만 받는다. 끝난 실행의
     구독은 닫혀 이후 게시를 받지 않는다. 지난 판본과 이미 소비한 신호의 재전달은
     기존 판본 규칙대로 재적용 없이 소비하거나 무시한다.
6. **메일박스 결속.** `AgentRunnerFactory`는 DI의 기본 메일박스를 주입한다.
   선언형 `execute()`와 로컬 위임은 factory를 거치지 않으므로,
   `AgentBootstrapValidationPostProcessor`가 bootstrap 때 컨테이너의 메일박스를
   `Agent.signal_mailbox`에 결속하고 `AgentRunner.for_agent_instance()`가 이를
   사용한다. 생성자로 주입한 `IAgentSignalSubscriber`가 우선한다.
   `AgentRunner.signal_mailbox`가 끝내 `None`이면 원장을 안전 지점에서만 다시
   읽고(시간 기반 폴링 없음), 진행 중 작업은 끊지 못하며, 새 입력을 기다려야 하는
   지점에서는 `AgentSignalMailboxConfigurationError`로 닫는다.

## 결과 (Consequences)

### 긍정적

- 신호가 없는 실행은 시작 시 1회 외에 원장을 조회하지 않는다. 동기 SELECT로 인한
  이벤트 루프 포화가 사라진다.
- 롤백된 신호로 깨어나지 않는다.
- 취소·긴급 입력은 모델 스트림을 즉시 닫고, 일반 조향은 응답을 낭비하지 않는다.

### 부정적

- 일반 조향은 진행 중 응답이 끝날 때까지 기다린다. 즉시 끊어야 하는 입력은
  생산자가 `URGENT`로 지정해야 한다.
- 실시간 전달은 같은 프로세스 안에서만 동작한다. 다른 프로세스의 생산자는 원장
  재생(다음 시작·재개) 또는 별도 publisher 구현에 의존한다.
- `IAgentSignalRepository`를 직접 구현하고 publisher를 부르지 않는 저장소는 실행 중
  신호를 전달하지 못한다.

## 검증

`core/spakky-agent/tests/unit/test_runner_mailbox.py`와 `test_mailbox.py`,
`plugins/spakky-sqlalchemy/tests/unit/test_agent_repository.py`와 acceptance test가
다음을 증명한다. 신호가 없는 동안 `list_pending` 추가 호출 0회, 커밋 뒤에만 깨움,
다른 스레드 신호로 깨어남, control 즉시 취소와 steering 안전 지점 주입, 중단 시 조향
보존, 지난 판본·재전달 거절.
