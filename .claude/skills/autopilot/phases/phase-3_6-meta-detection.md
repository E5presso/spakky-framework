# Phase 3.6: 자기 운영 결함 자동 감지·티켓화 (메타-자동화)

본 단계는 Phase 3 wave 종료 직후, Phase 3.5 회수 라운드와 짝을 이루어 활성화된다. logical-contradiction 시그널을 검사하여 매치되는 시그널마다 harness fix 티켓을 자동 생성하고, 본 실행의 다음 정상 wave 진입 전에 우선 머지되도록 큐에 편입한다. §3.5는 in-band 명시 spawn 회수, §3.6은 out-of-band 자기 운영 모순 자동 검출로 보완 관계.

본 phase의 §3.6-2 자동 티켓 생성 메커니즘은 Phase 1 dual-path 수렴 실패 시에도 entry point로 재사용된다 — 신규 메커니즘은 추가하지 않고 기존 entry point만 추가.

## 3.6-1. 감지 시그널 (logical-contradiction 기반)

자의적 wall-clock N분 임계값을 사용하지 않는다 — 모든 시그널은 **상태 모순**으로 정의된다 (`behavioral-guidelines.md` "자의적 임계값 금지" 정합).

| 시그널 | 모순 정의 |
|--------|-----------|
| **S1 monitor-stuck** | wave에서 미반환된 ticket의 `.process-state.json`에 `monitor_started`가 기록되어 있으나 PR이 이미 mergeable·CI green 상태임에도 `merged` 또는 `failed` 갱신이 없는 모순 — 시간 임계값이 아니라 "monitor가 머지 가능 상태를 관측하고도 전이를 안 함"으로 정의. |
| **S2 resume loop** | 동일 ticket_number에 대해 본 autopilot 실행이 §3-6 fallback resume 서브에이전트를 2회 이상 spawn한 상태 — 기록은 `wave_results[ticket].resume_count` 누적. 2회 spawn은 1회 fallback으로 해소되지 않음을 의미하므로 자체 모순. |
| **S3 직렬화 미작동** | 동일 파일 경로를 mutation하는 PR이 3개 이상 동시 OPEN인 상태. 본 스킬의 wave DAG는 쓰기 충돌을 직렬화해야 하므로 3개 이상 동시 OPEN은 DAG 분해 실패의 직접 증거. |
| **S4 state 부재/역행** | 워크트리는 존재하나 `.process-state.json`이 부재하거나, `pr_opened` 기록 후 `commit_done`만 다시 갱신되는 등 phase 키 역행 — process-ticket SSOT가 정의한 단조 증가 핸드오프와 모순. |
| **S5 consumer 미감지** | `monitor-pr` 산출 로그에 EVENT line이 emit된 흔적이 있는데 해당 ticket의 `.process-state.json`에 후속 phase 갱신이 없는 상태 — 이벤트 emit과 상태 전이 사이 모순 (회귀 SSOT는 monitor-pr 별도 티켓이며, 본 단계는 검출만 책임진다). |
| **S6 외부 봇 위반 카테고리 임계 누적** | §3-3-ter ledger의 어느 entry가 `count >= AUTOPILOT_BOT_VIOLATION_THRESHOLD` (default 3) 이고 `fired_ticket == null` 인 상태 — 자가 검토·pre-commit 게이트가 모두 통과한 PR이 외부 봇에서 같은 카테고리로 임계 회수 반복되어 잡혔다는 것은 로컬 게이트가 그 카테고리에 둔감하다는 패턴 모순. 임계 미만은 노이즈로 간주하므로 ledger만 갱신하고 시그널은 송신하지 않는다. |

각 시그널 검사는 wave 종료 시점에 메인 세션이 직접 수행한다 (서브에이전트 위임 시 컨텍스트 격리로 신호가 사라짐).

### 임계값 (S6 한정)

`AUTOPILOT_BOT_VIOLATION_THRESHOLD`는 환경 변수로 노출하며 default `3`이다. 3은 1회=우연·2회=동시기 사용자 동시 작업에서 흔히 발생·3회=구조적 갭의 패턴 경계로 운영 관찰 기반의 휴리스틱이며, 운영 데이터로 조정될 수 있다. 코드 내 하드코딩하지 않고 본 SKILL.md를 SSOT로 둔다 (`behavioral-guidelines.md` 정합 — 임계값을 silent assumption으로 박지 않고 본 § 본문에 근거와 함께 노출).

## 3.6-2. 자동 티켓 생성 + 큐 편입

매치된 시그널마다 `gh issue create`로 harness fix 티켓을 생성한다 (의사코드):

```
for signal in matched_signals:
  meta_ticket = gh issue create \
    --title "[Harness] autopilot self-detected: {signal.name} ({evidence_summary})" \
    --body "<harness_fix_template(signal)>"  # 시그널 정의 + 관찰 증거 + 회귀 시나리오 + 수정 대상 추정
    --milestone "<현재 마일스톤>" \
    --label "<현재 마일스톤에서 통용되는 harness fix 라벨 3종>"
  spawned_acc.add(meta_ticket.number)
  meta_queue.append(meta_ticket.number)
```

라벨은 하드코딩하지 않고 동일 마일스톤 내 기존 harness fix 티켓의 라벨 집합을 1회 조회하여 재사용한다 (`write-skill.md` "특정 사용자 login, 프로젝트 ID 등을 하드코딩하지 않는다" 원칙 준수).

**큐 편입 규칙**: 본 단계가 생성한 `meta_queue` 티켓은 다음 정상 wave 시작 전에 별도 메타 fix wave로 처리한다 — 정상 wave에 끼워넣으면 직렬화·DAG 분해 가정이 깨지므로 메타 fix는 단독 wave로 격리하여 머지 후 다음 정상 wave 진입.

**S6 후처리 (FR-005 중복 생성 가드)**: S6 시그널로 생성한 fix 티켓의 번호를 §3-3-ter ledger의 해당 entry `fired_ticket` 필드에 즉시 기록(`fired_at`도 함께)하여, 같은 카테고리가 다음 wave에서 또 임계 도달해도 중복 생성하지 않는다. fix 티켓이 머지된 뒤에도 동일 카테고리가 재발하면 별도 entry(라벨에 ` (v2)` suffix)로 신규 누적되므로 회귀 추적이 끊기지 않는다. 사용자에게 1줄 알림 (S6 1건당):

```
[autopilot] 외부 봇 위반 카테고리 임계 누적 → 하네스 fix 티켓 자동 생성: #{fix-ticket-number} (label="<라벨>", count=<N>)
```

## 3.6-3. 메인 세션 자체 처리 (서브에이전트 위임 금지)

본 §3.6 검사 루프는 **메인 세션이 자체 워크트리를 확보하고 직접 수행**한다. 서브에이전트 위임 시 다음 회귀가 발생한다:

- 서브에이전트가 monitor 도달 후 조기 종료하면 신호 관찰 자체가 사라진다.
- 신호 검사 결과를 메인 세션에 전달하는 핸드오프가 부재하다.

따라서:

1. **워크트리 자체 확보**: 메인 세션이 자체 워크트리를 1개 운영하며, 서브에이전트들이 만든 워크트리(`worktrees` 체크포인트 필드)를 read-only로 enumerate한다.
2. **monitor `until` polling 직접 수행**: 본 §3.6 검사 루프는 메인 세션이 시그널 매치 발생을 종료 조건으로 하는 `until` polling을 직접 수행한다. 본 § 한정 예외 — 본 SKILL.md 규칙 "autopilot 메인 세션은 직접 polling 금지"의 적용 대상은 PR 단위 monitor (process-ticket 책임)이며, 메타-감지 polling은 그 책임 경계 밖이다.
3. **서브에이전트는 fix 티켓 처리(`process-ticket`)에만 사용**. 검사 자체는 메인이 보존.

## 3.6-4. fixed-point 보장

`meta_queue`가 비어 있으면 Phase 3.5와 동일하게 다음 정상 wave 진입. 비어있지 않으면 메타 fix wave를 spawn하고, 메타 fix wave 종료 후 §3.6을 다시 실행한다 — 메타 fix가 또 다른 메타 시그널을 드러낼 수 있으므로 fixed-point까지 반복. 동일 시그널이 메타 fix wave 머지 후에도 재매치되면 charter §4-A 질의 트리거(분해 수렴 실패).
