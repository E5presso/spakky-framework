# Phase 3: 웨이브 실행 루프

각 웨이브 `w`를 순차적으로 처리한다.

## 3-1. 선행 웨이브 결과 확인 (read-only)

`w > 0`이면, `wave[w-1]` 종료 시점에 §3-4가 채운 skip 집합을 **참조만 한다** (BFS 재실행 금지). skip 집합에 속하지 않은 가지의 티켓만 wave[w]에 진입시킨다.

## 3-2. 병렬 진입

웨이브 내 각 티켓 `T`에 대해 **하나의 메시지에 복수 tool_use**로 서브에이전트를 동시 spawn한다. **`run_in_background: true` 강제** — wave 대기 = foreground subagent 반환 대기로 메인 turn을 점유하면 사용자 메시지가 즉시 수신되지 못해 무인 자동화의 사용자 인터럽트 가능성이 깨진다. **`team_name` + `name` 강제** — SendMessage 양방향 채널(§3-3-bis stuck probe / §3-6 fallback probe / §3-3 mid-flight 의도 보강 / §3-3-quater `ask-delegate` 처리)이 teammate name으로 라우팅되므로 name 미발급 시 본 채널 전체가 동작하지 않는다:

```
Agent(
  subagent_type: "general-purpose",
  team_name: "{TEAM_NAME}",
  name: "{T}",
  description: "process #{T}",
  run_in_background: true,
  permission_mode: "bypassPermissions",  # 메인 세션이 bypass 모드일 때만 명시 — §3-2-ter 조건부 inherit 절차 참조
  prompt: "**FIRST ACTION (do this before any other output)**: Use the `Skill` tool to invoke `process-ticket` with `args: \"{T} --auto-merge\"`. Do not output any analysis, plan, summary, or commentary before that tool call — meta-analysis without invoking the skill leaves the ticket unprocessed. If the `Skill` tool is not in your available toolset or the invocation errors, do NOT proceed silently — `SendMessage(to: \"team-lead\", summary: \"skill-unavailable {T}\", message: \"skill-unavailable: {T}\\nreason: <error 1줄>\")` 회신 후 종료. **Phase 6 monitor 절대 명령 (의역·완화 금지)**: 너는 자기 turn 안에서 직접 `monitor-pr/scripts/watch.sh`를 포그라운드 Bash로 호출하고, EVENT가 emit되면 같은 turn 안에서 case 분기 핸들러를 실행한 뒤 즉시 `watch.sh`를 다시 호출한다. **`reason in {merged, mergeable-clean, closed-without-merge, awaiting-human-review}`이면 즉시 DONE으로 간주 — 추가 `watch.sh` 호출 금지**. Phase 8 cleanup(`reason=merged`), Phase 7/8 자동 머지(`mergeable-clean`: `phase7_ready` 기록 후 같은 turn에서 `gh pr merge --squash --delete-branch`와 cleanup까지 완료; `phase7_ready`만 반환 금지), 결과 보고(`closed-without-merge`), 또는 `awaiting-human-review` 시 `status: awaiting-review` + `pending_human_comments: <bot CH2 코멘트 URL>` 보고를 수행 후 즉시 turn 종료한다. 위 4종 reason은 terminal 케이스이며 추가 cycle을 돌면 머지 후 dead time이 누적된다. 다음 4종 안티패턴 금지 — (1) `&` / `nohup` / `run_in_background: true` / `Monitor` / `ScheduleWakeup`로 띄우고 'monitor armed' 보고 후 종료, (2) '알림 대기' / '외부 이벤트 수신' / '사용자가 알려줄 것'으로 polling 위임, (3) 1~2 cycle 후 'CI 진행 중' / '변화 없음' / '오래 걸릴 것'으로 종료, (4) `watch.sh` stdout의 `reason` case 분기 없이 종료. SSOT는 `monitor-pr/SKILL.md` §'절대 명령'. **Root isolation guard**: Phase 3 이후 구현·검증·커밋 전 `process-ticket/scripts/assert_worktree_isolation.sh`가 실패하면 root checkout 오염 가능성이므로 즉시 failed 반환하고 root 변경을 자동 revert하지 않는다. **Monitor heartbeat ping**: `watch.sh`가 `EVENT reason=heartbeat`을 emit하면 (변화 없는 cycle 6회=3분 누적) 즉시 `SendMessage(to: \"team-lead\", summary: \"phase-tick {T}\", message: \"phase: monitor-pr | tick: poll <N> | pr=<#> | ci=<status> | review=<state>\")` 1줄 송신 후 같은 turn 안에서 watch.sh를 재호출하여 polling 재개 — 메인 세션이 monitor 루프를 hang으로 오판하지 않도록 보장. 본 ping은 단방향, 회신 대기 금지. 진행 중 charter §4-A/§4-B 질의 트리거 또는 behavioral-guidelines.md '스펙 검증 / 후속 티켓' 규칙으로 **신규 후속 GitHub 티켓을 생성한 경우**, 그 티켓의 구현은 **직접 분기하지 말고 autopilot에 번호만 보고**한다 (autopilot이 회수 라운드에서 처리). 사용자 질의가 필요한 경우(charter §4-A 트리거·plan 승인·review escalation 등)는 `AskUserQuestion`을 직접 호출하지 말고 `SendMessage`로 메인(team-lead)에 `ask-delegate`로 위임한다 — 단일 ledger 정합 (process-ticket SKILL.md '사용자 질의 위임' SSOT). **하네스 교정 (`.agents/skills/`·`.agents/rules/`·`AGENTS.md` 또는 동등 자산 변경 포함) 티켓은 plan summary를 `ask-delegate`로 질의하고 회신 수신 후에만 Phase 5 진입한다 — low-risk 자가 판정 무효** (process-ticket SKILL.md Phase 2 §2-1 SSOT). **Phase 전환 progress ping**: 각 Phase 진입 시점에 `SendMessage(to: \"team-lead\", summary: \"phase-ping {T}\", message: \"phase: <name> | issue: {T} | <1줄>\")` 1줄을 송신한다 — 정형·송신 시점은 process-ticket SKILL.md '*Phase 전환 progress ping*' SSOT. 본 ping은 단방향이며 회신을 기다리지 않는다. **Phase 내부 heartbeat + Blocker 즉시 emit**: 동일 phase 안에서 직전 ping 이후 3분+ 도구 호출이 누적되면 `phase: <name> | tick: <action> | <1줄>` 정형 heartbeat 1건 송신. CI fail·통합/유닛 test fail·triage decision 보류·환경 차단 발견 즉시 `phase: <name> | blocker: <kind> | <1줄>` 정형 blocker ping 1건 송신 (phase 종료 대기 금지). 정형·트리거는 process-ticket SKILL.md '*Phase 내부 heartbeat*' + '*Blocker 즉시 emit*' SSOT. **반환 형식**: process-ticket SKILL.md "서브에이전트 반환 형식 (강제)" 절의 canonical schema만 사용한다. `status`, `pr`, `issue`, `acceptance_check`, `issue_status`, `pending_human_comments`, `spawned` 라인을 모두 포함하고 산문·진행 로그·디버깅 로그는 반환하지 않는다."
)
```

`{T}`는 티켓 번호(예: `420`)를 그대로 사용하여 SendMessage `to: "420"` 라우팅의 키가 된다. resume 서브에이전트(§3-3-bis)는 `{T}-resume-<round>` 형식, 메타 fix 서브에이전트(§3.6-2)는 신규 META 티켓 번호를 그대로 사용한다.

> **상위 `run_in_background: true`와 prompt 안 안티패턴 (1) `run_in_background: true` 금지의 차이**: 상위 파라미터는 **autopilot 메인 → process-ticket 서브에이전트** spawn 형식이고(메인 턴 비점유 + background notification 수신), prompt 안 금지는 **process-ticket 서브에이전트 → Phase 6 monitor 루프**에서 자기 turn 안에 watch.sh를 포그라운드로 돌려야 한다는 내부 규율이다. 두 레이어는 충돌하지 않는다.

> **모델 지정 안 함**: autopilot은 서브에이전트 `model` 파라미터를 지정하지 않는다. process-ticket이 내부 Phase별로 직접 `opus/sonnet/haiku`를 선택한다 (process-ticket SKILL.md "모델 티어링" 섹션 참조).

## 3-2-bis. Agent Teams 인프라 발급 (SendMessage 양방향 채널 토대)

§3-2 첫 wave spawn 직전, 메인 세션이 1회 `TeamCreate(team_name, description)`을 호출하여 본 autopilot 호출의 team을 만든다. 본 team에 §3-2 spawn 서브에이전트, §3-3-bis resume 서브에이전트, §3-6 fallback resume 서브에이전트, §3.6-2 메타 fix 서브에이전트가 모두 속한다 — 메인 세션 하나에 다수 active team을 만들지 않는다.

**team_name 형식**: `autopilot-{normalized-arg}`. 인자(부모 이슈 번호·마일스톤명·티켓 목록)의 슬래시·공백·콤마를 hyphen으로 normalize. 예: `/autopilot 420` → `autopilot-420`.

```
TeamCreate(
  team_name: "{TEAM_NAME}",
  description: "autopilot wave orchestration for {arg}"
)
```

본 인프라가 없으면 SendMessage `to: <ticket-number>` 라우팅이 실패하므로, §3-3-bis probe·§3-6 probe·§3-3 mid-flight 보강·§3-3-quater `ask-delegate` 처리 모두 동작하지 않는다. 따라서 **TeamCreate 실패 시 §3-2 spawn을 거부하고 사용자에게 보고**한다 (charter §4-B "메인 블로커 회피 금지" 정합 — autopilot 자체 인프라가 깨진 상태로 진행하지 않는다).

team 정리는 Phase 6 최종 리포트의 워크트리 sweep 직후 `TeamDelete({team_name})` 1회로 수행한다 — 세션 종료 후 stale config가 다음 autopilot 호출과 충돌하지 않도록.

## 3-2-ter. 권한 모드 inherit (메인 → sub-agent 조건부 명시)

메인이 bypass permissions 모드이면 본 phase의 모든 `Agent({...})` spawn에 `permission_mode: "bypassPermissions"`를 명시한다. 일반 모드면 키를 생략한다. 모드 introspection API가 없으므로 autopilot 시작 시 1회 평가하여 같은 정책을 §3-2, §3-3-bis, §3-3-quinque, §3-6, §3.6-2 spawn에 일괄 적용한다. 명시 누락으로 `permission_request`가 메인 inbox에 도달하면 1회 승인 후 진행하되, 누적되면 시스템 트래픽 오염으로 보고한다.

## 3-3. 웨이브 완료 대기

**wave 대기 = background notification 수신 + 메인 세션은 그 사이 user-responsive 유지.** §3-2 spawn이 `run_in_background: true`이므로 메인 turn은 spawn 직후 종료된다(아래 1줄 알림 후). 메인 세션은 (a) 사용자가 보낸 메시지를 즉시 수신·응답할 수 있고, (b) 백그라운드 서브에이전트 완료 notification이 도착하면 wake되어 §3-3 결과 파싱·§3-3-ter ledger 누적·§3-3-bis stuck 감지 routine·§3-4 실패 전파·§3-5 다음 wave 진입을 수행한다. spawn 직후 1줄 알림 형식:

```
[autopilot] wave[{w}] spawn: {N}개 티켓 background 실행 중 ({tickets})
```

서브에이전트가 반환할 때까지 대기한다. 각 서브에이전트의 반환 값에서 다음을 파싱한다:
- `status`: `merged` | `awaiting-review` | `failed`
- `pr`: PR 번호 · URL (있으면)
- `issue`: GitHub Issue 번호
- `acceptance_check`: `PASS` | `partial` | `missing`
- `issue_status`: `Done` | `InReview` | `InProgress` | `Backlog` | `Cancelled`
- `pending_human_comments`: 사람 리뷰어 미응답 코멘트 링크 (`awaiting-review`이면 URL 목록, 아니면 `none`)
- `spawned`: 서브에이전트가 본 라운드에서 생성한 신규 후속 GitHub 티켓 번호 목록 (없으면 `none`) — §3-3-quinque에서 즉시 spawn, Phase 3.5는 누락 fallback.

**merge-gate-stuck 회수**: `status: blocked`, `status: awaiting-merge`, `merge approval required`, `phase7_ready without merged` 등 clean PR 병합 승인 대기 의미의 반환은 autopilot에서 유효한 차단 결과가 아니다. 사용자에게 묻지 않고 §3-6 fallback resume을 `process-ticket {T} --auto-merge`로 실행한다. 같은 티켓에서 2회 반복되면 SKILL.md S7 `merge-gate-stuck`으로 ledger 기록 + 메타 fix 티켓을 생성한다. 정상 하위 실행은 `DONE reason=mergeable-clean` 관찰 후 `phase7_ready`를 기록하더라도 그 상태를 반환하지 않고 같은 turn에서 Phase 8 merge/cleanup을 완료해 `status: merged`만 반환한다.

### 반환 형식 검증

process-ticket SKILL.md "서브에이전트 반환 형식 (강제)" 절의 정규형과 조건부 검사(`status: failed` → `failed_reason` 필수)를 그대로 적용한다. 불일치 시 §3-6 fallback으로 진입한다.

미준수 시 §3-6 fallback으로 진입한다 (재실행 또는 워크트리 체크포인트 회수). 미준수 사유가 merge approval 대기이면 사용자 질의 없이 `--auto-merge` resume만 허용한다.

반환 파싱 직후 `status == merged`인 티켓 번호를 실행 상태 사전의 `merged_children` 집합에 누적한다 — Phase 6 부모 자동 close 단계의 입력. 기존 §3-3 본문 동작은 변경하지 않으며 누적만 추가한다.

### 3-3-quinque. 후속 티켓 즉시 spawn (default)

**SSOT**: `behavioral-guidelines.md` "스펙 검증 / 후속 티켓" — `후속 티켓 자동 실행 default = 즉시 분해 (이벤트 트리거 기반). 본 세션 내 백그라운드 서브에이전트로 /process-ticket {신규-TICKET-NUMBER} 즉시 실행`. 본 §3-3-quinque은 그 SSOT를 autopilot 본문에 명시하는 절차 — wave 종료까지 spawn을 미루는 default는 본 SSOT 위반.

§3-3 반환 파싱에서 `spawned` 필드가 비어 있지 않으면(= `none` 이외) 메인 세션은 동일 turn 내에 다음을 수행한다:

1. `spawned` 라인의 번호 목록을 파싱하여 집합 `S`로 만든다.
2. 각 번호 `X ∈ S`에 대해 `gh issue view <X> --json state,labels,closedAt`로 현재 상태를 1회 확인한다.
   - `state == "closed"` → 이미 종결됨, spawn 생략 (idempotent).
   - 라벨 또는 PR 연결 상태로 다른 경로에서 이미 처리 중(`in-progress` / `in-review` 라벨) → spawn 생략 (race 회피).
   - 그 외(`backlog` / `todo`) → 즉시 spawn 대상.
3. 즉시 spawn 대상 번호 각각에 대해 §3-2 spawn 형식과 동일한 `Agent` tool 호출을 **단일 메시지의 복수 tool_use**로 동시 spawn한다. `team_name`은 §3-2-bis에서 발급한 동일 team을 재사용, `name`은 티켓 번호 `X` 그대로 사용. `run_in_background: true` 강제 — wave 진행을 차단하지 않는다.
4. spawn된 번호들을 실행 상태 사전의 `spawned_dispatched` 집합에 누적한다. Phase 3.5는 본 집합과 wave 전체에서 보고된 `spawned` 합집합을 비교하여 차집합(= 즉시 spawn이 누락된 번호)만 처리한다.
5. 사용자에게 1줄 알림 (spawn 1건 이상 시):

```
[autopilot] wave[{w}] 후속 spawn: {#X1, #X2, ...} ({N}개 background 실행)
```

**의존 관계 처리**: 후속 티켓의 `blockedBy`에 현재 wave의 PR 산출물에 의존하는 티켓이 들어 있으면, spawn된 sub-agent는 process-ticket Phase 1.5 blocker polling으로 자동 대기한다 (process-ticket SKILL.md "Phase 1.5: Blocker 확인 & 대기" SSOT). autopilot 메인이 별도 의존 dispatch 로직을 두지 않는다.

**Mid-flight 즉시 spawn**: §3-3 mid-flight 의도 보강 채널에서 sub-agent가 SendMessage로 `spawned: TICKET-NUMBER,...`를 wave 반환 전에 미리 보고하면, 메인은 본 §3-3-quinque 절차를 즉시 적용한다 (wave 반환을 기다리지 않는다). 후속 티켓을 만들고도 spawn 누락 채로 wave를 진행하는 결함의 1차 차단 경로.

### Mid-flight 의도 보강 (TaskStop + 다시 spawn 회피)

wave 진행 중 메인 세션이 (a) charter §4-A 질의 트리거 (스펙↔코드 직접 충돌, 도메인 사전 미등록 신규 어휘 등 — `charter.md` §4-A 인용)를 흡수하거나 (b) 사용자가 추가 지시를 보내면, 메인은 **TaskStop·다시 spawn 대신 SendMessage로 즉시 보강**한다.

#### 보강 메시지 정형

```
SendMessage(
  to: "{T}",
  summary: "intent-update {T}",
  message: "intent-update: {T}\ntrigger: <charter §4-A 질의 | 사용자 추가 지시>\ncontent: <보강 내용 — 5줄 이내, 산문 금지>\nbinding: <hard | advisory>"
)
```

- `binding: hard` — sub-agent는 본 보강을 받기 전에 행한 결정이라도 본 보강과 충돌하면 롤백 후 재진행한다 (예: 잘못된 도메인 사전 어휘 사용 → 어휘 교체 + 영향 라인 수정).
- `binding: advisory` — sub-agent는 본 보강을 다음 phase 진입 전 1회 검토 후 채택 여부를 결정한다 (예: 사용자가 "테스트 fixture 위치도 같은 디렉토리로 옮겨줘" 추가 지시).

#### TaskStop + 다시 spawn 유지 조건 (예외)

다음 두 케이스에 한해 SendMessage 보강 대신 TaskStop + 다시 spawn 흐름 유지:

1. **워크트리 격리 깨짐**: sub-agent가 잘못된 워크트리에 진입했거나 루트 리포지토리에서 직접 mutation하는 흔적이 워크트리 enumerate에서 관찰됨 — 본 케이스는 컨텍스트 자체가 오염되었으므로 메시지 보강으로 회수 불가능.
2. **티켓 분해 단위 재정의**: charter §4-A의 "티켓 분해 단위 재정의 필요" 트리거가 sub-agent의 현 작업 범위를 무효화 — sub-agent의 컨텍스트가 새 티켓 범위와 매핑되지 않으므로 메시지 보강은 헛됨.

본 두 케이스 외 모든 charter §4-A 트리거는 SendMessage 보강이 default — 컨텍스트 손실 비용이 명백한 경우가 아닌 한 TaskStop은 회피한다.

## 3-3-bis. wave 대기 중 워크트리 state 집계 — stuck 능동 감지 routine

§3-3은 "서브에이전트가 반환할 때까지 대기"만 명시할 뿐, **반환 자체가 영원히 오지 않는 케이스**(서브에이전트가 monitor 루프 안에서 정지·hang·context 소진하여 종료 메시지조차 보내지 못하는 상황)를 다루지 않는다. §3-6은 "이미 반환된 비정상 종료"를 회수하지만, 미반환 stuck은 다른 채널로 감지해야 한다. 본 routine은 wave 대기 중 워크트리 `.process-state.json`을 주기적으로 enumerate하여 **논리적 모순 상태**(반환 책임을 다한 것으로 보이는데 미반환)인 서브에이전트를 식별하고 resume 서브에이전트를 spawn한다.

### 동작

§3-3 wave 대기 동안 stuck-enumerate 간격(60초, monitor-pr 30초 watch cadence와 무관)으로 다음을 수행한다. autopilot 메인 polling 금지 규칙(SKILL.md "autopilot 메인 세션은 직접 polling 금지")은 PR 상태에 대한 적용이며, 워크트리 파일 enumerate + GitHub 외부 단발 조회는 polling 루프가 아닌 stuck 감지 단발 query이므로 본 routine은 그 규칙과 충돌하지 않는다.

1. **워크트리 enumerate**: `git worktree list --porcelain`으로 현재 활성 워크트리 목록을 수집. 본 wave에서 spawn한 티켓 번호에 해당하는 워크트리만 대상.
2. **state 파일 읽기**: 각 워크트리의 `.process-state.json`을 Read. 파일 부재 시 그 티켓은 §3-6 fallback 영역(워크트리 진입 전 종료) — 본 routine 대상에서 제외.
3. **메타데이터 집계**: 티켓 번호는 branch name parse(`feat/420-...` → `420`), `commit_done` / `push_done` / `pr_opened` / `monitor_started` / `phase7_ready` / `merged` / `failed` 필드 존재 여부, `updated_at` ISO timestamp.

### Stuck 판정 — 논리적 모순 검출 (자의적 timeout 임계값 금지)

다음 모순 중 **하나라도 충족**하면 stuck 후보로 분류한다. 본 판정은 wall-clock timeout이 아니라 "서브에이전트의 책무가 끝났는데 반환이 없다"는 논리적 모순이다 — `behavioral-guidelines.md` "자의적 임계값 금지" 정합:

- **모순 A (PR 종결 미반영)**: `state.pr_opened.number` 존재 + `state.merged` / `state.failed` 부재 상태에서 `gh pr view <number> --json mergeable,state,mergeStateStatus` 단발 조회 결과가 `state == "MERGED"` 또는 `state == "CLOSED"`. 즉 PR이 외부에서 이미 종결되었는데 서브에이전트가 그 사건을 흡수해 반환하지 못한 모순. monitor-pr의 책무 경계상 PR 종결 = 반환 트리거다.
- **모순 B (DIRTY/CONFLICTING 회피 불능)**: `state.monitor_started` 존재 + `state.merged` 부재 상태에서 `gh pr view <number>`가 `mergeStateStatus == "DIRTY"` 또는 `mergeable == "CONFLICTING"`. monitor-pr 루프는 DIRTY 감지 시 conflict resolution 분기로 진입하여 결국 반환해야 한다(charter §4-B "메인 블로커 회피 금지" 적용 영역). DIRTY 상태가 관찰되는데 서브에이전트가 같은 wave 대기 큐에서 미반환이면 그 분기 자체가 진행되지 않고 있는 상태 = stuck.
- **모순 C (auto-merge clean terminal 미흡수)**: `state.monitor_started` 존재 + `state.merged` / `state.failed` 부재 상태에서 `gh pr view <number> --json mergeable,state,mergeStateStatus,statusCheckRollup` 단발 조회 결과가 `state == "OPEN"`, `mergeStateStatus in {"CLEAN","UNSTABLE"}`, `pendingChecks == 0`, `failedChecks == 0`이면 stuck 후보로 분류한다. 이 상태는 `monitor-pr`의 `DONE reason=mergeable-clean` terminal 조건과 동일하며, autopilot 하위 `/process-ticket --auto-merge`는 `phase7_ready` 기록 후 Phase 8 squash merge + cleanup까지 같은 turn에서 완료해야 한다. `monitor_started` 또는 `phase7_ready`만 남고 wave 반환이 없으면 병합 승인 대기가 아니라 resume 대상이다.

`gh pr view`는 본 routine 단일 인터벌마다 stuck 후보당 1회만 호출 — 백오프 polling 루프가 아니다 ("메인 polling 금지" 규칙과의 정합성). 모순 C의 `pendingChecks` / `failedChecks` 계산은 `monitor-pr/scripts/watch.sh`와 동일하게 `statusCheckRollup`에서 완료 전 check와 실패/에러 conclusion을 세며, 외부 리뷰 봇 workflow(`Claude Auto PR Code Review`, `Claude Code Review`, `Codex Code Review`) 실패는 review-event 경로가 담당하므로 CI 실패 카운트에서 제외한다.

### SendMessage probe (오감지 false positive 방지)

모순 A/B/C 충족 시점에 sub-agent가 사실은 정상 진행 중일 가능성(예: conflict resolution 분기 안에서 git pull · 충돌 수정 · 재push을 거치는 wall-clock 긴 분기 진입 직후, 또는 clean terminal을 관찰하고 Phase 8 병합 명령에 진입한 직후)이 있다. 즉시 새 resume sub-agent를 spawn하면 worktree·PR을 동시에 mutation하여 race를 일으킨다. 본 절은 spawn 분기 진입 전 **SendMessage probe (생존 확인 메시지)** 1회를 강제하여 false positive를 회수한다.

#### probe 메시지 정형 (5줄 이내, 산문 금지)

```
SendMessage(
  to: "{T}",
  summary: "stuck-probe {T}",
  message: "stuck-probe: {T}\nreason: <모순 A | 모순 B | 모순 C>\nevidence: <pr_state=MERGED/CLOSED | mergeStateStatus=DIRTY | mergeStateStatus=CLEAN pendingChecks=0 failedChecks=0 등 1줄>\nrequest: 현재 phase, 진행 blocker, ETA를 5줄로 회신"
)
```

probe를 포함해 메인이 실행 중인 process-ticket sub-agent에게 SendMessage를 보낸 경우, 같은 티켓의 워크트리 경로를 알고 있으면 SendMessage 직후 `<worktree>/.monitor-interrupt` 파일을 쓴다. monitor-pr `watch.sh`는 이 sentinel을 감지하면 `EVENT reason=interrupt`로 반환하고, sub-agent turn이 종료되면서 방금 보낸 메시지가 inbox로 배달된다. 순서는 항상 **SendMessage 먼저, sentinel write 나중**이다. 대상 sub-agent가 아직 Phase 6에 도달하지 않았으면 Phase 6 진입 시 stale sentinel을 지우므로 안전하다.

#### probe-ack (probe acknowledgment, 응답) 정형

sub-agent는 다음 형식으로 회신한다 (산문 금지):

```
probe-ack: {T}
phase: <Phase 6 monitor | Phase 6 conflict-resolution | ...>
blocker: <1줄>
eta: <상태 전이 트리거 1줄 — "CI green 도달 시" 등>
```

`eta`는 wall-clock이 아니라 **상태 전이 트리거 어휘**로 표현한다 — `behavioral-guidelines.md` "휘발성 스케줄러 절대 금지" / 본 phase "자의적 임계값 금지" 정합.

#### 무응답 판정 (자의적 timeout 금지)

probe 발송 후 다음 §3-3-bis enumerate 인터벌(60초)까지 메시지 큐에 응답이 도착하지 않으면 무응답으로 간주. 본 정의는 wall-clock 60초가 아니라 "다음 enumerate cycle까지" — 본 routine의 자체 cadence와 일치하므로 새 임계값을 도입하지 않는다.

#### 분기 결정

- **응답 정상**: probe-ack 정형 충족 + ETA가 모순 A/B/C 해소를 함의함 → spawn 생략. 다음 enumerate 인터벌에서 같은 sub-agent의 state 전이를 재확인. 동일 티켓 probe는 wave당 최대 3회 (3회 enumerate cycle 동안 false positive 회수에 충분).
- **응답 stuck 자인**: probe-ack에서 sub-agent가 `blocker`로 명시 stuck 상태를 진술 → SendMessage로 의도 보강 메시지 1회 전송 (예: "DIRTY 상태에서 conflict resolution 분기 이어가, watch.sh DONE까지 turn 종료 금지"). 다음 enumerate cycle에서 state 전이 없으면 spawn 분기 진입.
- **무응답** (3 cycle 누적): 아래 "Resume 서브에이전트 spawn" 분기 진입.

### Resume 서브에이전트 spawn

stuck 후보로 식별된 티켓에 대해 §3-2 spawn 형식과 동일한 단일 메시지의 tool_use로 새 서브에이전트를 spawn한다. **prompt에 PR 식별자 + 마지막 known state 필드를 명시 인자로 넘겨 monitor 단계를 이어받게 한다** (SKILL.md "서브에이전트가 monitor 도달 전 조기 종료한 경우" 규칙 정합):

```
Agent(
  subagent_type: "general-purpose",
  description: "resume #{T}",
  run_in_background: true,
  permission_mode: "bypassPermissions",  # §3-2-ter 조건부 inherit — 메인 세션이 bypass 모드일 때만 명시
  prompt: "Invoke the /process-ticket skill with argument '{T} --auto-merge'. 워크트리 `<path>`가 이미 존재하며 `.process-state.json`이 다음 상태를 기록하고 있다: pr_opened={pr.number}, monitor_started={ts}, phase7_ready={phase7_ready|null}, merged=null. PR `#{pr.number}`가 외부에서 {모순 A/B/C 사유}로 stuck 상태이므로 monitor 단계를 이어받아 처리(필요 시 clean terminal이면 Phase 8 auto-merge부터 즉시 진행, DIRTY이면 conflict resolution 후 재push)하고 wave 반환 형식으로 응답하라. **Phase 6 monitor 절대 명령**: 너는 자기 turn 안에서 직접 `monitor-pr/scripts/watch.sh`를 포그라운드 Bash로 호출하고 EVENT는 같은 turn 안에서 case 분기로 처리한다. DONE(merged/mergeable-clean/closed-without-merge/awaiting-human-review)이 나올 때까지 turn 종료 금지. `&`/`nohup`/`run_in_background: true`/`Monitor`/`ScheduleWakeup` 사용 금지, '알림 대기'·'외부 이벤트 수신'·1~2 cycle 후 종료 금지, `reason` case 분기 없는 종료 금지. SSOT는 `monitor-pr/SKILL.md` §'절대 명령'. `DONE reason=mergeable-clean` 또는 기존 `phase7_ready`는 반환 사유가 아니라 Phase 8 진입 조건이다. `phase7_ready`만 기록하고 반환하지 말고 같은 turn에서 `gh pr merge --squash --delete-branch`와 cleanup까지 완료하라. **Monitor heartbeat ping**: `watch.sh`가 `EVENT reason=heartbeat`을 emit하면 (변화 없는 cycle 6회=3분 누적) 즉시 `SendMessage(to: \"team-lead\", summary: \"phase-tick {T}\", message: \"phase: monitor-pr | tick: poll <N> | pr=<#> | ci=<status> | review=<state>\")` 1줄 송신 후 같은 turn 안에서 watch.sh를 재호출하여 polling 재개 — 메인 세션이 monitor 루프를 hang으로 오판하지 않도록 보장. 본 ping은 단방향, 회신 대기 금지. **반환 형식**은 §3-2와 동일."
)
```

resume 서브에이전트가 반환하면 §3-3과 동일하게 결과를 파싱하고 wave_results에 적용한다. 단, **stuck 검출 → resume spawn → resume 반환** 사이클은 동일 티켓당 1회로 제한한다 (회귀 무한 루프 방지). resume 서브에이전트도 stuck하면 §3-6 fallback 또는 charter §4-A 질의로 escalate.

resume spawn 직후 사용자에게 1줄 알림(스팸 방지 — wave당 최대 1회 집계):

```
[autopilot] wave[{w}] stuck 감지: {N}개 티켓 resume 서브에이전트 spawn ({tickets})
```

본 routine은 stuck 미관찰 wave에서는 활성화되지 않으며 (모순 충족 0건 → spawn 0건), 정상 경로 동작을 변경하지 않는다.

## 3-3-ter. 외부 봇 위반 카테고리 누적 (durable ledger)

wave 내 PR이 머지되면, 그 PR의 외부 봇(예: claude[bot]) 리뷰 코멘트를 카테고리로 정규화하여 durable ledger에 누적한다. 자가 검토(`/review-code`)와 pre-commit 게이트가 모두 통과한 PR이 외부 봇에서야 위반을 받는다는 것은 로컬 게이트의 구조적 갭이며, 같은 카테고리가 임계 회수만큼 반복되면 갭은 우연이 아닌 패턴이다. 본 누적이 §3.6-1 S6 시그널의 입력이 된다.

### Ledger SSOT (단일 진입점)

- **경로**: `~/.claude/projects/-Users-spakky-Documents-projects-spakky-framework/state/bot-violation-ledger.json`. 세션 종료 후에도 유지되는 durable 위치 — `behavioral-guidelines.md` "휘발성 스케줄러 절대 금지" 정합. 본 path가 ledger의 유일한 SSOT이며, 다른 위치(메모리 / 워크트리 state / 임시 파일)에 분기 누적하지 않는다.
- **누적 진입점**: 본 §3-3-ter 1곳. `monitor-pr` LISTENING 루프·`triage-comments`·다른 phase에서 누적하지 않는다 — 중복 카운트 방지(FR-002 정합).
- **스키마** (배열의 각 entry):

```json
{
  "label": "<짧은 카테고리명, 한국어 우선>",
  "count": 3,
  "evidence": [
    { "pr": "<PR URL>", "comment_id": <id>, "ticket": "<TICKET-NUMBER>" }
  ],
  "fired_ticket": "<TICKET-NUMBER 또는 null>",
  "fired_at": "<ISO-8601 timestamp 또는 null>"
}
```

`fired_ticket`이 null이면 미spawn 상태, 비어있지 않으면 spawn 상태(중복 spawn 가드).

### 누적 절차 (PR 머지 직후 1회)

§3-3에서 `wave_results[T].status == merged`인 각 티켓 `T`에 대해 메인 세션이 직접 수행:

1. **외부 봇 코멘트 수집**: `gh api repos/E5presso/spakky-framework/pulls/<PR>/reviews` + `repos/.../pulls/<PR>/comments` + `repos/.../issues/<PR>/comments`로 모든 코멘트를 수집하고 `user.login`이 봇 계정(`claude[bot]` 등 `[bot]` 접미)인 항목만 필터링. 본인이 단 reply 마커(`<!-- claude-agent-reply to=<id> -->`)가 본문에 포함된 항목은 자기 응답이므로 제외.
2. **위반 추출**: 각 봇 코멘트가 위반 지적인지 LLM으로 판정. 단순 정보·승인·"LGTM" 류는 제외. 위반 1건당 (위반 핵심 1줄 요약, 코멘트 id, PR URL, ticket number) 튜플을 만든다.
3. **카테고리 정규화 (LLM)**: 메인 세션이 LLM으로 위반 요약을 짧은 한국어 카테고리 라벨로 정규화한다. 입력에는 ledger의 기존 라벨 목록을 함께 제공하여 동의어가 같은 라벨로 합쳐지도록 한다 (예: "function-level import"·"인라인 import" → 같은 라벨). 라벨 어휘를 사전 고정하지 않는다 — LLM이 일관된 짧은 명사구를 생성하도록 프롬프팅(FR-003 정합).
4. **ledger 갱신**: 매치된 라벨이 ledger에 존재하면 `count += 1` + `evidence` append. 없으면 신규 entry 생성(`count = 1`, `fired_ticket = null`). `fired_ticket != null`인 entry는 별도 entry(예: 라벨에 ` (v2)` suffix)로 신규 누적하여 이전 fix 머지 후 회귀를 추적 가능하게 한다.
5. **파일 쓰기**: 표준 atomic write — 임시 파일에 쓴 뒤 `mv`로 덮어쓰기. 동시 실행 중인 다른 autopilot 세션과의 race는 본 스킬이 메인 세션 단일 진입을 강제하므로(§3.6-3) 발생하지 않는다.

ledger 디렉토리 부재 시 `mkdir -p`로 생성. 파일 부재 시 빈 배열(`[]`)로 초기화.

> **휘발성 경로 금지**: ledger를 메모리(`feedback_*.md`)·워크트리 `.process-state.json`·세션 한정 임시 파일에 저장하지 않는다. 위 SSOT 경로 외 모든 누적 위치는 세션 종료 시 사라져 약속 유기와 동등하다 (`behavioral-guidelines.md` "휘발성 스케줄러 절대 금지" 정합).

## 3-3-quater. ask-delegate 메시지 처리

wave 대기 중 sub-agent가 SendMessage로 `ask-delegate` 메시지를 보내면 메인 세션이 처리 분기를 적용한다. 분기 본문(self_check Yes/No 판정 + 직렬 처리)은 process-ticket SKILL.md "사용자 질의 위임 → 메인 처리 분기" SSOT를 그대로 따른다 — 본 절은 분기 정의를 중복하지 않는다.

본 처리는 wave 진행 중 언제든 발생 가능 — 메인 세션이 user-facing 채널을 점유 중이므로, 같은 turn 내에 `AskUserQuestion`을 호출하더라도 다른 sub-agent의 background 진행을 방해하지 않는다 (sub-agent는 자기 turn 안에서 진행 중이며 메인 turn 차단과 무관).

## 3-3-sextus. wave 반환 외부 검증 routine (자기 보고 ↔ 사실 어긋남 차단)

§3-3에서 sub-agent가 `status: merged` 반환을 보냈더라도 그 보고가 사실과 어긋날 수 있다 — GitHub state가 실제로는 closed가 아니거나, 티켓 본문 명세 중 일부만 처리되고 나머지가 누락된 채 머지된 케이스. 본 routine은 wave 반환 파싱 직후 메인 세션이 PR diff와 GitHub state를 직접 외부 검증하여 어긋남을 차단한다.

### 적용 대상

§3-3 wave 반환 파싱 직후, `wave_results[T].status == merged` 인 모든 티켓에 대해 메인 세션이 직접 수행. `awaiting-review` / `failed` / `partial`은 이미 미완 상태로 분류된 결과이므로 본 routine 대상이 아니다.

### 검증 1: PR diff vs 본문 수용 기준 grep 라인

1. `gh pr view <PR> --json body,files` 단발 조회.
2. PR 본문의 "Acceptance Criteria (자가 grep)" 섹션을 회수 (process-ticket Phase 4.5가 첨부). 섹션이 비어 있으면 GitHub 이슈 본문에서 직접 grep 라인 추출 (Phase 4.5와 동일 추출 규칙).
3. 메인이 각 grep 라인을 머지된 develop tip에서 직접 실행하여 기대값 일치를 재검증.
4. 미충족 1건 이상 → 어긋남 검출.

### 검증 2: GitHub state 일치

1. `gh issue view <T> --json state,closedAt,labels` 단발 조회.
2. `state != "closed"` (close 아님) → 어긋남 검출.

### 어긋남 시 분기 (§3.6-2 entry point 재사용 — 중복 구현 금지)

검증 1 또는 검증 2 어긋남 1건 이상이면 §3.6-2 자동 티켓 생성 메커니즘을 그대로 호출하여 후속 fix 티켓을 spawn한다. 본 routine은 신규 메커니즘을 추가하지 않는다 — entry point만 추가:

- **검증 1 어긋남**: `signal.name = "wave-return-acceptance-mismatch"`, evidence = 미충족 grep 라인 + PR URL + 머지 commit hash.
- **검증 2 어긋남**: `signal.name = "wave-return-github-state-mismatch"`, evidence = `state` 실제값 + 티켓 URL.

생성된 fix 티켓 번호는 `meta_queue`에 편입하여 다음 정상 wave 진입 전에 별도 메타 fix wave로 처리한다 (§3.6-2 큐 편입 규칙 그대로 적용).

검증 2 어긋남의 경우 메타 fix 티켓 분기와 별도로, 메인이 즉시 `gh issue close <T>`로 강제 전이 + 재조회하여 즉시 보정한다 (process-ticket Phase 8 §3-bis와 동일 로직). 메타 fix 티켓은 "왜 자기 보고가 어긋났는지" 근본 원인 추적용이며, 보정은 즉시 수행하여 마일스톤 진척도가 흔들리지 않게 한다.

사용자에게 1줄 알림 (어긋남 1건당):

```
[autopilot] wave[{w}] 외부 검증 어긋남: #{T} {signal.name} → 메타 fix 티켓 #{fix-id} 큐 편입
```

본 routine은 §3-3-ter 외부 봇 위반 누적과 직교한다 — 외부 봇 위반은 PR 머지 후 외부에서 들어오는 코멘트 패턴 누적, 본 routine은 sub-agent 자기 보고 자체의 어긋남 검출.

## 3-4. 실패 전파

웨이브 내 어느 티켓이 `failed` 또는 `awaiting-review`(사람 응답 대기)이면, 그 티켓을 `blockedBy`로 가지는 **후속 웨이브의 티켓(전이적 포함)**을 `skipped`로 표시한다. 즉 `A→B→C` 체인에서 A가 차단되면 B와 C 모두 skip. 구현: 차단 집합에서 BFS로 후속 노드를 전부 skip 집합에 넣는다. 독립 가지는 계속 진행한다.

## 3-5. 다음 웨이브

모든 서브에이전트가 반환한 뒤 `w := w + 1`. 모든 웨이브가 끝나면 Phase 3.5로 진행.

## 3-6. 서브에이전트 비정상 종료 fallback (`.process-state.json` 회수)

서브에이전트가 monitor 도달 전 종료(반환 형식 위반 / mid-thought 종료 / context 한도 도달 외 사유로 status 누락)하면, 메인 세션이 직접 추론으로 진행 상태를 메우지 않는다. 워크트리 루트의 `.process-state.json` 체크포인트(process-ticket SKILL.md "상태 핸드오프" 절)를 읽어 resume 지점을 결정한다.

### SendMessage probe 우선 (sub-agent 생존 확인)

워크트리 enumerate에서 `.process-state.json`이 존재하고 sub-agent가 wave 반환 형식 위반·mid-thought 종료 등으로 메인의 wave 결과 큐에 도달하지 못한 케이스에 대해, 메인은 새 sub-agent spawn 또는 watch.sh 떠맡기 분기 진입 전에 **SendMessage probe**로 sub-agent 생존을 우선 확인한다. sub-agent가 외부 TaskStop으로 잠시 멈춘 상태이거나 monitor 분기 안에서 wall-clock 긴 호출 진행 중이면 spawn은 worktree race를 야기하므로 본 probe로 false positive를 회수한다.

#### probe 메시지 정형

```
SendMessage(
  to: "{T}",
  summary: "resume-probe {T}",
  message: "resume-probe: {T}\nreason: 반환 형식 위반 또는 빈 결과\nstate: <pr_opened.number=N | merged 부재>\nrequest: 중단된 phase 이어가, 정규 반환 형식으로 응답"
)
```

#### 응답 처리

- **응답 도착** + sub-agent가 정규 반환 형식으로 회신: wave_results에 그대로 적용하고 spawn 생략.
- **응답이 진행 의사** (예: `phase: Phase 6 monitor / blocker: CI pending / eta: CI green`)인데 정규 반환은 아직 미발생: SendMessage로 "wave 반환 형식 강제" 의도 보강 1회 전송 → 다음 §3-3-bis enumerate cycle 까지 대기 → state 전이 또는 정규 반환 도착 시 wave_results 적용.
- **무응답** (다음 enumerate cycle): 아래 분기로 진입 — 단 메인 watch.sh 떠맡기 분기는 삭제되고 resume sub-agent spawn으로 대체된다 (autopilot SKILL.md `규칙` 정합).
- **명시적 종료 자인** (sub-agent가 SendMessage로 `terminated: <reason>` 회신): 즉시 resume sub-agent spawn 분기 진입.

```
worktree=$(ls -d <repo-root>/.claude/worktrees/<branch>)
state=$(cat "$worktree/.process-state.json" 2>/dev/null || echo "{}")
```

resume 분기:

1. `state.merged` 존재 → 이미 머지 완료. `wave_results[ticket]`에 `status=merged`로 누적하고 다음 wave 진행. (서브에이전트가 반환 직전에만 죽은 케이스.)
2. `state.pr_opened.number` 존재 + `state.merged` 부재 → resume sub-agent spawn (§3-2 spawn 형식과 동일하지만 prompt에 PR 식별자·마지막 known state 명시). 메인 watch.sh 떠맡기 분기는 사용하지 않는다 — autopilot SKILL.md `규칙` ("autopilot 메인 세션은 직접 polling 금지") + ("monitor 도달 전 종료 시 resume sub-agent spawn") 정합. resume sub-agent가 monitor 단계를 이어받아 정규 반환 형식으로 응답하면 wave_results에 적용.
3. `state.pr_opened` 부재 → Phase 5 도달 전 종료. `wave_results[ticket]`에 `status=failed`, `failed_reason=process-ticket terminated before PR creation`으로 기록하고 §3-4 실패 전파 적용 (또는 같은 wave에 1회 다시 spawn — fixed-point 진입 방지를 위해 동일 티켓을 다시 spawn하는 것은 1회로 제한, 2회 연속 실패 시 질의). 다시 spawn 시에도 §3-2와 동일하게 `run_in_background: true`로 spawn한다.
4. `state.failed` 존재 → `wave_results[ticket]`에 `status=failed`, `failed_reason=state.failed.reason`으로 기록.

`.process-state.json` 자체가 부재하면(서브에이전트가 워크트리 진입 전 종료) §3 fallback 케이스로 간주하여 동일 티켓 1회 다시 spawn. 2회 연속 부재 시 질의.

**fallback 진입 시 사용자에게 1줄 알림** (스팸 방지를 위해 wave당 최대 1회 집계):

```
[autopilot] wave[{w}] fallback: {fallback_count}개 티켓이 process-state로 회수됨 ({merged_via_state}/{probed_resumed}/{re_dispatched})
```
