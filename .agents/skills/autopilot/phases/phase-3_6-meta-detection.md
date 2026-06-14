# Phase 3.6: 자기 운영 결함 자동 감지·이슈화 (메타-자동화)

본 단계는 Phase 3 wave 종료 직후, Phase 3.5 회수 라운드와 짝을 이루어 활성화된다. logical-contradiction 시그널을 검사하여 매치되는 시그널마다 harness fix 이슈를 자동 생성하고, 본 실행의 다음 정상 wave 진입 전에 우선 머지되도록 큐에 편입한다. §3.5는 in-band 명시 spawn 회수, §3.6은 out-of-band 자기 운영 모순 자동 검출로 보완 관계.

본 phase의 §3.6-2 자동 이슈 생성 메커니즘은 Phase 1 dual-path 수렴 실패 시에도 entry point로 재사용된다 — 신규 메커니즘은 추가하지 않고 기존 entry point만 추가.

## 3.6-1. 감지 시그널 (logical-contradiction 기반)

자의적 wall-clock N분 임계값을 사용하지 않는다 — 모든 시그널은 **상태 모순**으로 정의된다 (`feedback_no_arbitrary_thresholds.md` 원칙 준수).

| 시그널 | 모순 정의 |
|--------|-----------|
| **S1 monitor-stuck** | wave에서 미반환된 ticket의 `.process-state.json`에 `monitor_started`가 기록되어 있으나 PR이 이미 mergeable·CI green 상태임에도 `merged` 또는 `failed` 갱신이 없는 모순 — 시간 임계값이 아니라 "monitor가 머지 가능 상태를 관측하고도 전이를 안 함"으로 정의. |
| **S2 resume loop** | 동일 issue_number에 대해 본 autopilot 실행이 §3-6 fallback resume 서브에이전트를 2회 이상 spawn한 상태 — 기록은 `wave_results[issue].resume_count` 누적. 2회 spawn은 1회 fallback으로 해소되지 않음을 의미하므로 자체 모순. |
| **S3 직렬화 미작동** | 동일 파일 경로를 mutation하는 PR이 3개 이상 동시 OPEN인 상태. 본 스킬의 wave DAG는 쓰기 충돌을 직렬화해야 하므로 3개 이상 동시 OPEN은 DAG 분해 실패의 직접 증거. |
| **S4 state 부재/역행** | 워크트리는 존재하나 `.process-state.json`이 부재하거나, `pr_opened` 기록 후 `commit_done`만 다시 갱신되는 등 phase 키 역행 — process-ticket SSOT가 정의한 단조 증가 핸드오프와 모순. |
| **S5 consumer 미감지** | `monitor-pr` 산출 로그에 EVENT line이 emit된 흔적이 있는데 해당 ticket의 `.process-state.json`에 후속 phase 갱신이 없는 상태 — 이벤트 emit과 상태 전이 사이 모순 (회귀 SSOT는 monitor-pr 별도 이슈이며, 본 단계는 검출만 책임진다). |
| **S6 외부 봇 위반 카테고리 임계 누적** | §3-3-ter ledger(`ledger-bot-violations.md`)의 어느 entry가 `count >= AUTOPILOT_BOT_VIOLATION_THRESHOLD` (default 3) 이고 `fired_issue == null` 인 상태 — 자가 검토·pre-commit 게이트가 모두 통과한 PR이 외부 봇에서 같은 카테고리로 임계 회수 반복되어 잡혔다는 것은 로컬 게이트가 그 카테고리에 둔감하다는 패턴 모순. 임계 미만은 노이즈로 간주하므로 ledger만 갱신하고 시그널은 송신하지 않는다. |
| **S7 monitor-entry-idle** | sub-agent가 `idle_notification` 송신 + 워크트리 `.process-state.json`에 `pr_opened.number` 기록 + `monitor_started` 부재 — PR을 만들고도 monitor watch.sh를 시작하지 않은 채 turn 종료한 모순. process-ticket Phase 6 진입 의무(자기 turn 안에서 watch.sh 포그라운드 호출 + DONE까지 turn 종료 금지)의 직접 위반 증거. **어휘 트리거 확장**: 마지막 phase ping 본문에 `monitor armed` / `watch.sh entering` / `watch.sh preparing` / `monitor ready` / `about to poll` 류 turn-boundary 어휘 + 직후 `idle_notification` 도달이면 `monitor_started` 갱신 여부와 무관하게 본 모순으로 분류 — 동작 시작 어휘(`watch.sh started, polling pr=#N`)가 아닌 ping은 watch.sh 미호출의 강한 신호이며 state write race의 false negative를 차단한다. wave 진행 중 `idle_notification`이 도달할 때마다 즉시 검사한다 (wave 종료 시점만 기다리면 사용자가 발견할 때까지 무한 idle). |
| **S8 commit-without-push** | sub-agent가 Phase 5 commit-pr ping 송신 + 워크트리 git 상태에 `staged` 변경 또는 `local commit ahead of upstream` 존재 + `pr_opened` 부재 — commit-pr phase에 진입했으나 실제 commit 또는 push가 누락된 모순. push 누락은 PR 생성·CI 실행·triage 모두를 silent하게 차단하므로 자동 감지 필수. wave 진행 중 phase ping이 `Phase 5` 또는 `commit-pr`을 명시한 후 다음 phase ping 없이 idle 진입 시 즉시 검사. |
| **S9 merged-without-terminal-return** | sub-agent가 `idle_notification` 송신 + 워크트리 `.process-state.json`에 `merged` 기록 + 메인이 해당 sub-agent의 정규형 terminal 반환(`status:` 라인으로 시작하는 §3-3 반환 형식)을 `SendMessage`로 미수신 (background teammate는 plain text 출력을 메인에 전달하지 않으며 정규형 terminal 반환은 `SendMessage`로만 도달 — process-ticket SKILL.md "서브에이전트 반환 형식 (강제)" §"전달 채널" SSOT) — PR은 머지되었으나 wave 결과 반환이 누락된 모순. `gaps_detected` / `gaps_dispatched` / `acceptance_check` 정규형 라인을 회수하지 못해 §3-3-quinque 검증 3(gap-defer 차단)이 불완전해진다. S1과 달리 monitor 전이가 아니라 terminal 반환 emit 자체의 누락이며, 머지 후 `state.merged` 존재로 `phase-3-wave-loop.md` §3-3-bis 모순 A를 빠져나가는 케이스의 동등 신호. wave 진행 중 `idle_notification` 수신 즉시 검사. |

각 시그널 검사는 wave 종료 시점에 메인 세션이 직접 수행한다 (서브에이전트 위임 시 컨텍스트 격리로 신호가 사라짐). **단 S7/S8/S9는 wave 진행 중 `idle_notification` 수신 즉시 1회 추가 검사** — wave 종료까지 누적하면 회복이 사용자 발견에 의존하게 된다.

### 임계값 (S6 한정)

`AUTOPILOT_BOT_VIOLATION_THRESHOLD`는 환경 변수로 노출하며 default `3`이다. 3은 1회=우연·2회=동시기 사용자 동시 작업에서 흔히 발생·3회=구조적 갭의 패턴 경계로 운영 관찰 기반의 휴리스틱이며, 운영 데이터로 조정될 수 있다. 코드 내 하드코딩하지 않고 본 SKILL.md를 SSOT로 둔다 (`feedback_no_arbitrary_thresholds.md` 정합 — 임계값을 silent assumption으로 박지 않고 본 § 본문에 근거와 함께 노출).

## 3.6-2. 자동 이슈 생성 + 큐 편입

매치된 시그널마다 **plan-issues sub-agent를 spawn하여 harness fix 이슈를 생성**한다 — 메인이 `gh issue edit 또는 GitHub connector 갱신` create 호출을 직접 수행하지 않는다 (`new-ticket-intake.md` §3-3-octies-1 "plan-issues sub-agent 경유 의무" 정합). 본 § 메타 fix 이슈 생성은 §3-3-octies-1 적용 대상이며 그 예외 enumeration에 포함되지 않는다.

```
for signal in matched_signals:
  Agent(
    subagent_type: "general-purpose",
    team_name: <§3-2-bis 발급 동일 team>,
    name: f"plan-issues-meta-{signal.name}-{wave_idx}",
    description: f"plan-issues for meta fix: {signal.name}",
    run_in_background: true,
    permission_mode: <§3-2-ter 조건부 명시>,
    prompt: """Invoke /plan-issues with the signal artifact as direction input.
      signal.name: <signal.name>
      signal.evidence_summary: <evidence_summary>
      signal.harness_fix_template: <harness_fix_template(signal) — 시그널 정의 + 관찰 증거 + 회귀 시나리오 + 수정 대상 추정>
      metadata_anchor (autopilot Phase 1 확정):
        team: <Phase 1에서 확정한 대상 팀>
        project: <현재 autopilot 인자가 속한 project>
        milestone: <현재 마일스톤>
        assignee: <source 이슈 assignee 또는 "me">
        priority: 2  # High
        labels: <동일 마일스톤 내 기존 harness fix 이슈의 라벨 집합 1회 조회 후 재사용>
      산출 issue number 목록을 'plan-issues-complete' SendMessage 정형으로 team-lead에 회신.
      issue title은 "[Harness] autopilot self-detected: <signal.name> (<evidence_summary>)" 형식으로 시작."""
  )
```

메인 세션은 plan-issues sub-agent의 `plan-issues-complete` 회신을 `new-ticket-intake.md` §3-3-octies-3 절차로 처리한다 — metadata 검증 → spawn pool enqueue → drain spawn. 산출 issue number는 `spawned_acc`와 `meta_queue`에 누적되며 metadata 검증 실패 시 `meta_issue_metadata_failed`에 기록한다. metadata 보정의 `save_issue` update 호출은 `new-ticket-intake.md` "update 호출 공통 면제"에 따라 허용된다.

라벨은 하드코딩하지 않고 동일 마일스톤 내 기존 harness fix 이슈의 라벨 집합을 1회 조회하여 plan-issues sub-agent에 인자로 전달한다 (`write-skill.md` "특정 사용자 login, 프로젝트 ID 등을 하드코딩하지 않는다" 원칙 준수).

**메타데이터 검증 실패 분기**: plan-issues 회신 후 `get_issue` 재조회에서 `project`·`milestone`·`assignee`·필수 라벨 중 하나라도 누락되면 §3-3-octies-3 절차로 1회 `save_issue` update 호출 보정 후 재조회한다. 2차 재조회도 실패하면 해당 meta issue를 `meta_queue`에 넣지 않고 `meta_issue_metadata_failed`에 기록한다. 최종 리포트에 누락 필드와 issue URL을 노출하며, 라벨/마일스톤/assignee가 빈 하네스 fix 이슈를 자동 처리 wave에 넣지 않는다.

**큐 편입 규칙**: 본 단계가 생성한 `meta_queue` 이슈은 다음 정상 wave 시작 전에 별도 메타 fix wave로 처리한다 — 정상 wave에 끼워넣으면 직렬화·DAG 분해 가정이 깨지므로 메타 fix는 단독 wave로 격리하여 머지 후 다음 정상 wave 진입. 메타 fix sub-agent spawn도 Phase 3 §3-2-quater의 `concurrency_limit = 5` spawn pool을 공유하며, §3-2 wave spawn 형식을 그대로 사용하므로 drain 직전 메인 세션이 §3-2-quinquies 워크트리 선생성 절차를 수행하고 `WORKTREE_ABS` 인자 슬롯을 채운다. active slot이 없으면 `meta_queue`에 머무르며, 기존 active sub-agent 1건이 terminal 반환을 보낼 때 다음 1건만 drain한다.

**S6 후처리 (FR-005 중복 생성 가드)**: S6 시그널로 생성한 fix 이슈의 ID를 §3-3-ter ledger의 해당 entry `fired_issue` 필드에 즉시 기록(`fired_at`도 함께)하여, 같은 카테고리가 다음 wave에서 또 임계 도달해도 중복 생성하지 않는다. fix 이슈이 머지된 뒤에도 동일 카테고리가 재발하면 별도 entry(라벨에 ` (v2)` suffix)로 신규 누적되므로 회귀 추적이 끊기지 않는다. 사용자에게 1줄 알림 (S6 1건당):

```
[autopilot {N_done}/{M} ({P}%) ETA {Xh Ym}] 외부 봇 위반 카테고리 임계 누적 → 하네스 fix 이슈 자동 생성: <fix-issue-number> (label="<라벨>", count=<count>)
```

prefix 정형은 SKILL.md "진행률 정형" SSOT 인용. `count`는 본 카테고리의 누적 위반 건수이며 prefix의 진행률 변수와 충돌하지 않는다.

## 3.6-3. 메인 세션 자체 처리 (서브에이전트 위임 금지)

본 §3.6 검사 루프는 **메인 세션이 자체 워크트리를 확보하고 직접 수행**한다. 서브에이전트 위임 시 다음 회귀가 발생한다:

- 서브에이전트가 monitor 도달 후 조기 종료하면 신호 관찰 자체가 사라진다.
- 신호 검사 결과를 메인 세션에 전달하는 핸드오프가 부재하다.

따라서:

1. **워크트리 자체 확보**: 메인 세션이 자체 워크트리를 1개 운영하며, 서브에이전트들이 만든 워크트리(`worktrees` 체크포인트 필드)를 read-only로 enumerate한다.
2. **monitor `until` polling 직접 수행**: 본 §3.6 검사 루프는 메인 세션이 시그널 매치 발생을 종료 조건으로 하는 `until` polling을 직접 수행한다. 본 § 한정 예외 — 본 SKILL.md 규칙 "autopilot 메인 세션은 직접 polling 금지"의 적용 대상은 PR 단위 monitor (process-ticket 책임)이며, 메타-감지 polling은 그 책임 경계 밖이다.
3. **서브에이전트는 fix 이슈 처리(`/process-ticket`)에만 사용**. 검사 자체는 메인이 보존.

## 3.6-4. fixed-point 보장

`meta_queue`가 비어 있으면 Phase 3.5와 동일하게 다음 정상 wave 진입. 비어있지 않으면 메타 fix wave를 spawn하고, 메타 fix wave 종료 후 §3.6을 다시 실행한다 — 메타 fix가 또 다른 메타 시그널을 드러낼 수 있으므로 fixed-point까지 반복. 동일 시그널이 메타 fix wave 머지 후에도 재매치되면 charter §4-A 질의 트리거(분해 수렴 실패).
