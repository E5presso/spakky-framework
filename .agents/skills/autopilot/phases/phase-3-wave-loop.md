# Phase 3: 웨이브 실행 루프

각 웨이브 `w`를 순차 처리한다. 본 phase 내 모든 `[autopilot ...]` 1줄 알림의 prefix는 SKILL.md "진행률 정형" SSOT(출력 직전 자가검사 포함)를 따른다.

## 3-1. 선행 웨이브 결과 확인 (read-only)

`w > 0`이면 `wave[w-1]` 종료 시점에 §3-4가 채운 skip 집합을 **참조만 한다** (BFS 재실행 금지). skip 집합에 속하지 않은 가지의 이슈만 wave[w]에 진입시킨다.

## 3-2. 병렬 진입

웨이브 내 각 이슈 `T`는 §3-2-quater spawn pool을 통해 서브에이전트로 진입한다. **`concurrency_limit = 5` 강제** (drain pattern). **`run_in_background: true` 강제** — foreground 반환 대기는 메인 turn을 점유하여 사용자 인터럽트 가능성을 깬다. **`team_name` + `name` 강제** — SendMessage 양방향 채널(§3-3-bis probe / §3-6 probe / mid-flight 보강 / §3-3-quater ask-delegate)이 teammate name으로 라우팅된다:

```
Agent(
  subagent_type: "general-purpose",
  team_name: "{TEAM_NAME}",
  name: "{T}",
  description: "process {T}",
  run_in_background: true,
  permission_mode: "bypassPermissions",  # §3-2-ter 조건부 명시
  prompt: "**FIRST TOOL CALL (deferred 스키마 선로드 — 단일 호출)**: 너의 맨 처음 tool 호출은 반드시 `ToolSearch(query: \"select:SendMessage,Skill\")` 하나여야 한다. 본 작업에서 쓰는 `Skill`·`SendMessage`는 deferred tool이라 첫 사용 시점에 스키마가 지연 로드되는데, 그 지연 로드가 tool-definition prefix를 변이시켜 직전 prompt-cache(~78K tok)를 무효화한다. spawn 직후 1회의 `ToolSearch`로 두 스키마를 한꺼번에 선로드하면 prefix 변이가 spawn 시점 1회로 결정론적 고정되어, 이후 `Skill`·`SendMessage` 호출이 추가 prefix 변이·캐시 무효화를 일으키지 않는다. 이 선로드 외에 다른 tool을 먼저 호출하거나 분석·요약을 출력하지 않는다. **FIRST ACTION (선로드 직후)**: Use the `Skill` tool to invoke `process-ticket` with `args: \"{T} --auto-merge\"`. Do not output any analysis, plan, summary, or commentary before that tool call — meta-analysis without invoking the skill leaves the ticket unprocessed. If the `Skill` tool is not in your available toolset or the invocation errors, do NOT proceed silently — `SendMessage(to: \"team-lead\", summary: \"skill-unavailable {T}\", message: \"skill-unavailable: {T}\\nreason: <error 1줄>\")` 회신 후 종료. **WORKTREE_ABS (메인 세션이 선생성 완료)**: `{WORKTREE_ABS}` (branch `{BRANCH}`). `/create-worktree`·자체 `git worktree add` 호출 금지 — hook이 차단하여 Phase 3에서 stall한다. 본 절대경로만 사용하고 모든 git/파일 도구는 `worktree-isolation.md` §2 패턴(`git -C \"{WORKTREE_ABS}\"` / 절대경로)으로 호출한다. **Phase 6 monitor**: `monitor-pr/SKILL.md` §'절대 명령' + `process-ticket/phases/phase-6-monitor.md` 계약을 의역·완화 없이 그대로 적용 — 요약본 없음, binding (포그라운드 watch.sh·terminal reason 즉시 DONE·금지 안티패턴/어휘·monitor-start ping·heartbeat ping·turn 종료 자가검사 전부 포함). **commit/push 검증 ping**: process-ticket SKILL.md 정형(`commit-start`/`push-done`) 의무 — push-done 없이 idle 진입은 §3-3-bis 모순 D 트리거. **신규 후속 이슈**: 구현을 직접 분기하지 말고 autopilot에 `spawned: ISSUE-NUMBER,...`로만 보고한다. **사용자 질의**: `사용자 질의` 직접 호출 금지 — `SendMessage` `ask-delegate`로 team-lead 위임 (process-ticket SKILL.md '사용자 질의 위임' SSOT). 하네스 교정 이슈(`.agents/skills/`·`.agents/rules/`·`AGENTS.md` 또는 동등 자산 변경 포함)은 plan summary를 `ask-delegate`로 질의하고 회신 수신 후에만 Phase 5 진입 — low-risk 자가 판정 무효 (process-ticket Phase 2 §2-1 SSOT). **ask-delegate 자가판정 선행**: 송신 전 `behavioral-guidelines.md` 자가검사 (a)(b)(c) 의무 — 셋 다 Yes면 위임 금지, 자판정+근거를 PR 본문에 기록. gap 분해는 자가판정 대상 아님(즉시 분해 default·`gaps_dispatched` 의무 불변). charter §4-A 트리거(스펙↔코드 직접 충돌·도메인 사전 미등록 신규 어휘·이슈 분해 단위 재정의·destructive)만 위임. **Phase 4 리뷰 격리**: teammate 컨텍스트라 `Agent` tool 부재 — `/review-code` in-context 수행 금지, `review-delegate` 정형으로 team-lead에 위임 후 turn 종료(idle), `review-result` 수신 후 재개 (process-ticket SKILL.md '리뷰 위임 (sub-agent 한정)' SSOT). **progress ping**: 'Phase 전환 progress ping'·'Blocker 즉시 emit' 정형 의무 (process-ticket SKILL.md SSOT, 단방향·회신 대기 금지). **반환**: process-ticket SKILL.md '서브에이전트 반환 형식 (강제)' 정규형 — `gaps_detected`/`gaps_dispatched` 라인은 gap 유무와 무관 필수(없으면 `none`), terminal 반환은 `SendMessage(to: \"team-lead\", summary: \"terminal-return {T}\", message: <정규형 본문>)`로 1회 emit한 뒤에만 idle 허용. 머지·`worktree-cleanup-req` 송신은 작업 종료가 아니다 — 생략 시 §3-3-bis 모순 E 트리거."
)
```

`{T}`는 이슈 번호 그대로 — SendMessage `to:` 라우팅 키. resume 서브에이전트(§3-3-bis)는 `{T}-resume-<round>`, 메타 fix(§3.6-2)는 신규 META 이슈 번호. `{WORKTREE_ABS}`/`{BRANCH}`는 §3-2-quinquies 선생성 절차가 확정 — spawn 직전 메인이 채운다.

> 상위 `run_in_background: true`(메인 → process-ticket spawn 형식)와 prompt 내부 monitor 포그라운드 규율(sub-agent → watch.sh)은 레이어가 달라 충돌하지 않는다.
> **모델**: wave spawn은 `model` 미지정 — 전 Phase 혼재이므로 process-ticket 내부 티어링(process-ticket SKILL.md "모델 티어링")을 따른다. 상태 흡수형 resume의 `model: sonnet` 명시는 §3-3-bis 템플릿 + SKILL.md "규칙" 참조.

## 3-2-bis. Agent Teams 인프라 발급

§3-2 첫 wave spawn 직전 메인이 1회 호출한다. 본 phase의 모든 spawn(§3-2·§3-3-bis·§3-6·§3.6-2)이 이 단일 team에 속한다 — 메인 하나에 다수 active team 금지. **team_name 형식**: `autopilot-{normalized-arg}` (인자의 슬래시·공백·콤마 → hyphen).

```
TeamCreate(team_name: "{TEAM_NAME}", description: "autopilot wave orchestration for {arg}")
```

본 인프라 없이는 SendMessage `to: <issue-number>` 라우팅 전체(probe·mid-flight 보강·ask-delegate 처리)가 동작하지 않는다 — **TeamCreate 실패 시 spawn 거부 + 사용자 보고** (charter §4-B "메인 블로커 회피 금지"). team 정리는 Phase 6 워크트리 sweep 직후 `TeamDelete({team_name})` 1회 — stale config가 다음 호출과 충돌하지 않도록.

## 3-2-ter. 권한 모드 (조건부 명시)

- 메인이 bypass permissions 모드 → 본 phase 모든 spawn(§3-2·§3-3-bis·§3-3-quinque·§3-3-septies·§3-6·§3.6-2)에 `permission_mode: "bypassPermissions"` 명시 / 메인이 일반 모드 → 키 누락(권한 prompt가 사용자에게 직접 도달) / 모드 판별 모호 → 명시 (키가 무시되는 환경에서도 호출은 무해하나, 명시 누락발 sub-agent hang이 더 비싼 비대칭).
- 명시 누락 시 sub-agent 도구 호출이 `permission_request`로 메인 inbox 도달 → plain text "approved" 1회 회신 후 진행. 누적되면 user-facing 채널이 시스템 트래픽으로 오염되므로 명시가 1차 차단 default.

## 3-2-quater. Spawn pool semaphore + drain pattern

`concurrency_limit = 5`는 Phase 3 전체 단일 pool("지금 running 중인 process-ticket 계열 sub-agent 수")에 적용한다. §3-2 wave spawn·§3-3-bis resume·§3-3-quinque 후속 spawn·§3-6 fallback resume·§3.6-2 메타 fix 모두 같은 pool을 공유한다 — active 5이면 queue 대기, terminal 반환 1건당 다음 1건만 drain.

1. wave 진입 시 `pending_spawn_queue`에 DAG 순서로 적재, `active_spawn_count < 5` 동안 최대 5건 spawn.
2. 한 메시지에 spawn tool_use 최대 5개 — 6건 이상 동시 포함 금지 (server-side burst limiter가 worktree 진입 전 dead 상태를 만든다).
3. terminal 반환(`merged|awaiting-review|failed`) 수신 → `active_spawn_count -= 1` + queue에서 다음 1건 spawn.
4. 후속/resume/메타 fix 요청은 새 queue를 만들지 않는다 — 현재 wave queue 뒤에 append, 같은 count 공유.
5. stuck/fallback resume은 terminal 반환을 기다리지 않는다 — probe 무응답 또는 명시 종료 자인 확정 시 원본을 `superseded` 표시 + slot 회수 후 resume enqueue. 원본이 뒤늦게 반환하면 무시하고 resume 반환만 wave_results에 반영.
6. pool 상태는 메인 실행 상태 사전(`active_spawn_ids`·`superseded_spawn_ids`·`pending_spawn_queue`·`spawned_pending`·`spawned_dispatched`·`resume_dispatched`·`meta_queue`)에 둔다 — sub-agent `.process-state.json`과 분리.
7. drain 알림은 batch 압축 — `spawned/total`·`active`·`queued` 포함 1줄.

## 3-2-quinquies. 워크트리 선생성 (모든 spawn 형식 공통)

`worktree-isolation.md` §1(생성·정리 = 메인 책무)·§2(sub-agent는 절대경로를 spawn-prompt 인자로 수신) + hook의 sub-agent `worktree add` 차단에 따라, 본 phase **모든 spawn 형식**은 spawn 직전 메인이 워크트리를 선생성하고 `WORKTREE_ABS` 슬롯으로 전달한다. "§3-2 형식과 동일"로 참조하는 절은 본 절차와 슬롯을 함께 상속한다. `EnterWorktree` 호출 금지 — 부모/형제 cwd 변이.

`Agent(...)` 호출 직전 1회:

1. **branch 해석**: `T`의 GitHub `gitBranchName` (예: `feat/420`). resume은 원본 branch 재사용 — 같은 PR 이어받기, 새 branch 금지.
2. **기존 워크트리 검사**: `git -C <repo-root> worktree list --porcelain` — 존재 + resume/fallback 경로(§3-3-bis·§3-6): 재사용 (`.process-state.json` 보존) / 존재 + 신규 spawn 경로(§3-2·§3-3-quinque·§3.6-2): stale — `git -C <repo-root> worktree remove <abs-path> --force` 후 재생성.
3. **생성 (신규 한정)**: `git -C <repo-root> worktree add <repo-root>/.claude/worktrees/<branch> -b <branch> origin/develop`. branch ref 잔존 시 `-b` 생략, 기존 branch 체크아웃.
4. `WORKTREE_ABS = <repo-root>/.claude/worktrees/<branch>` 확정 → prompt 슬롯 주입.

## 3-3. 웨이브 완료 대기

wave 대기 = background notification 수신. 메인은 그 사이 user-responsive를 유지하고, notification 도착 시 wake되어 결과 파싱·§3-3-ter ledger 누적·§3-3-bis stuck 감지·§3-4 실패 전파·§3-5 다음 wave 또는 §3-2-quater drain을 수행한다.

spawn 직후 1줄 알림: `[autopilot {N}/{M} ({P}%) ETA {Xh Ym}] wave[{w}] spawn: {spawned}/{total}개 이슈 background 실행 중 active={active} queued={queued} ({tickets})`

반환 파싱 필드: `status`(`merged|awaiting-review|failed`) / `pr`(번호·URL) / `pending_human_comments`(사람 리뷰어 미응답 코멘트 링크) / `spawned`(신규 후속 이슈 번호 목록, 없으면 `none` — §3-3-quinque 즉시 spawn, Phase 3.5는 누락 fallback).

### 반환 형식 검증

process-ticket SKILL.md "서브에이전트 반환 형식 (강제)" 정규형. 1차 검증 정규식:

```
^status: (merged|awaiting-review|failed)$
^pr: (#\d+ \(https?://[^)]+\)|none)$
^issue: [A-Z]+-\d+$
```

미준수 → §3-6 fallback. 파싱 직후 `status == merged`인 ID를 `merged_children`에 누적한다 (Phase 6 부모 자동 Done 입력).

### 3-3-quinque. 후속 이슈 즉시 spawn (default) + 메타데이터 계약 (절차 SSOT)

**SSOT**: `behavioral-guidelines.md` "스펙 검증 / 후속 이슈" — 후속 이슈 자동 실행 default = 즉시 분해. wave 종료까지 spawn을 미루는 것은 SSOT 위반. 본 절의 메타데이터 검증·보정 절차는 후속 이슈 계약의 단일 SSOT — SKILL.md "후속 이슈 GitHub 메타데이터 계약"·phase-1 §3-bis·`new-ticket-intake.md` §3-3-octies-3·phase-3_5가 본 절을 인용한다.

§3-3 반환의 `spawned`가 `none`이 아니면 메인은 동일 turn 내에 수행한다:

1. `spawned` ID 목록 → 집합 `S`.
2. 각 `X ∈ S`: `gh issue view 또는 GitHub connector 조회({ id: X, includeRelations: true })` 1회 — `statusType ∈ {completed, canceled}` → spawn 생략(idempotent) / `{started, inReview}` → 생략(race 회피) / 그 외(`backlog`/`unstarted`/`triage`) → spawn 대상.
3. queue 편입 전 **메타데이터 계약 검증**. 기대값 = `issue_metadata_by_id[T]`(source 이슈 snapshot — phase-1 §3-bis) 1차, 빈 필드는 `autopilot_metadata_context` fallback:
   - `project`/`projectMilestone`: 기대값과 동일해야 함 — 누락/불일치 시 `gh issue edit 또는 GitHub connector 갱신` 보정 + 재조회.
   - `assignee`: source assignee 동일 보정. source 부재 + 실행 주체 명확 시 `assignee: "me"` fallback.
   - `labels`: source 라벨 최소 집합 보존, source가 비면 동일 마일스톤/부모 라벨 샘플. 미존재 라벨명 생성 금지 — 해당 라벨만 제외 후 `metadata_warning` 기록.
   - `relations.blockedBy`: 현재 PR 산출물 직접 의존이 명시(sub-agent 명시 또는 `gaps_dispatched` 근거)된 경우만 `T`를 blocker로 포함 — 임의 blocker 금지.
4. 보정 후 재조회 검증 — 통과 → spawn 유지 / 실패 → `metadata_violation[X]` 기록 + §3.6-2로 `signal.name = "spawned-issue-metadata-mismatch"` fix 이슈 생성, `X`는 `spawned_pending`이 아닌 `spawned_metadata_blocked`에 보관. 메타데이터 빈 이슈를 실행 큐에 넣지 않는다.
5. 검증 통과 ID를 §3-2-quater `pending_spawn_queue`에 추가 — §3-2-bis 동일 team 재사용, `name = X`, `run_in_background: true`, §3-2 spawn 형식 + §3-2-quinquies 선생성. active slot이 있으면 같은 turn에서 5건 한도로 즉시 drain.
6. enqueue ID → `spawned_pending`, 실제 `Agent(...)` 호출까지 drain된 ID → `spawned_dispatched`. Phase 3.5는 wave 전체 `spawned` 합집합과 `spawned_dispatched`의 차집합(즉시 spawn 누락분)만 처리.
7. 알림 (spawn 1건+ 시): `[autopilot ...] wave[{w}] 후속 spawn queue: {X1, X2, ...} active={active} queued={queued}` / 보류 발생 시: `[autopilot ...] wave[{w}] 후속 이슈 메타데이터 보류: {X1, ...} (누락: 실제 필드)`.

**의존 처리**: 후속 이슈 `blockedBy`가 현재 wave PR 산출물을 가리키면 spawn된 sub-agent의 process-ticket Phase 1.5 blocker polling이 자동 대기한다 — 메인 별도 의존 dispatch 로직 금지.

**Mid-flight 즉시 spawn**: sub-agent가 wave 반환 전 SendMessage로 `spawned:`를 미리 보고하면 본 절차를 즉시 적용한다 (반환 대기 금지) — spawn 누락 채 wave 진행을 막는 1차 차단 경로.

### Mid-flight 의도 보강 (TaskStop + 재spawn 회피)

wave 진행 중 메인이 (a) charter §4-A 질의 트리거를 흡수하거나 (b) 사용자 추가 지시를 받으면, TaskStop·재spawn 대신 SendMessage로 즉시 보강한다:

```
SendMessage(
  to: "{T}",
  summary: "intent-update {T}",
  message: "intent-update: {T}\ntrigger: <charter §4-A 질의 | 사용자 추가 지시>\ncontent: <보강 내용 — 5줄 이내, 산문 금지>\nbinding: <hard | advisory>"
)
```

- `binding: hard` — 보강 전 결정이라도 충돌하면 롤백 후 재진행. `binding: advisory` — 다음 phase 진입 전 1회 검토 후 채택 결정.
- **TaskStop + 재spawn 유지 예외 (이 2건만)**: ① 워크트리 격리 깨짐(잘못된 워크트리 진입·루트 직접 mutation 흔적 — 컨텍스트 오염, 메시지로 회수 불가) ② 이슈 분해 단위 재정의(§4-A 트리거가 현 작업 범위를 무효화 — 컨텍스트가 새 범위와 매핑되지 않음). 그 외 모든 §4-A 트리거는 SendMessage 보강이 default.

## 3-3-bis. wave 대기 중 워크트리 state 집계 — stuck 능동 감지 routine

§3-3 대기는 **반환 자체가 영원히 오지 않는 케이스**(monitor 안 정지·hang·context 소진)를 다루지 못하고, §3-6은 "이미 반환된 비정상 종료"만 회수한다. 본 routine은 wave 대기 중 일정 간격(60초)으로 워크트리 `.process-state.json`을 enumerate하여 논리적 모순 상태의 서브에이전트를 식별하고 resume을 spawn한다. SKILL.md "메인 직접 polling 금지"는 PR 상태에 대한 적용 — 워크트리 파일 enumerate + 외부 단발 조회는 stuck 감지 단발 query로 충돌하지 않는다.

1. `git worktree list --porcelain`으로 본 wave spawn 이슈의 워크트리만 수집.
2. 각 워크트리 `.process-state.json` Read — 부재 시 §3-6 fallback 영역(워크트리 진입 전 종료)으로 제외.
3. 집계: 이슈 번호 = branch name parse(`#NNNN-...` → `#NNNN`), `commit_done`/`push_done`/`pr_opened`/`monitor_started`/`phase7_ready`/`merged`/`failed` 존재 여부, `updated_at`.

### Stuck 판정 — 논리적 모순 검출 (자의적 timeout 금지)

wall-clock timeout이 아니라 "책무가 끝났는데 반환이 없다"는 논리적 모순으로 판정한다 (`behavioral-guidelines.md` "자의적 임계값 금지"). 하나라도 충족 시 stuck 후보:

- **모순 A (PR 종결 미반영)**: `state.pr_opened.number` 존재 + `state.merged`/`state.failed` 부재 + `gh pr view <number> --json mergeable,state,mergeStateStatus` 단발 조회 = `MERGED`|`CLOSED` — PR 종결은 monitor-pr 책무상 반환 트리거인데 미반환.
- **모순 B (DIRTY/CONFLICTING 회피 불능)**: `state.monitor_started` 존재 + `state.merged` 부재 + `mergeStateStatus == "DIRTY"` 또는 `mergeable == "CONFLICTING"` — conflict resolution 분기가 진행되지 않는 상태 (charter §4-B "메인 블로커 회피 금지" 적용 영역).
- **모순 C (auto-merge clean terminal 미흡수)**: `state.monitor_started` 존재 + `state.merged`/`state.failed` 부재 상태에서 `gh pr view <number> --json mergeable,state,mergeStateStatus,statusCheckRollup` 단발 조회 결과가 `state == "OPEN"`, `mergeStateStatus in {"CLEAN","UNSTABLE"}`, `pendingChecks == 0`, `failedChecks == 0`이면 stuck 후보로 분류한다. 이 상태는 `monitor-pr`의 `DONE reason=mergeable-clean` terminal 조건과 동일하며, autopilot 하위 `/process-ticket --auto-merge`는 `phase7_ready` 기록 후 Phase 8 squash merge + cleanup까지 같은 turn에서 완료해야 한다. `monitor_started` 또는 `phase7_ready`만 남고 wave 반환이 없으면 병합 승인 대기가 아니라 resume 대상이다.
- **모순 D/E**: 정의 SSOT는 `phase-3_6-meta-detection.md` §3.6-1 표 — **D = S8(commit-without-push), E = S9(merged-without-terminal-return)**. 검사 시점: wave 종료 대기 없이 즉시 — E는 `idle_notification` 수신 즉시, D는 Phase 5/commit-pr ping 후 추가 ping 없는 idle 즉시. 대응: D는 probe → resume 분기, E는 아래 terminal-return-probe — E는 `gh pr view` 불호출 (`state.merged`로 머지 확정, worktree·PR race 없음).

`gh pr view`는 인터벌마다 stuck 후보당 1회만 — 백오프 polling 루프가 아니다. 모순 C의 `pendingChecks`/`failedChecks` 계산은 `monitor-pr/scripts/watch.sh`와 동일하게 `statusCheckRollup`에서 완료 전 check와 실패/에러 conclusion을 세며, 외부 리뷰 봇 workflow(`Claude Auto PR Code Review`, `Claude Code Review`, `Codex Code Review`) 실패는 review-event 경로가 담당하므로 CI 실패 카운트에서 제외한다.

> **interrupt-idle은 stuck이 아니다**: `reason=interrupt` yield(`monitor-pr/SKILL.md` §"Interrupt — 능동 지시 yield")는 모순 A~E 어디에도 해당하지 않는다. 메인은 자신이 보낸 SendMessage+sentinel이 유발한 idle임을 알므로 resume을 발동하지 않는다 — idle 직후 그 지시가 새 turn으로 monitoring을 재개시킨다.

### SendMessage probe (false positive 방지 — §3-6 공통 절차 SSOT)

모순 충족 시점에도 sub-agent가 정상 진행 중일 수 있다(예: conflict resolution의 wall-clock 긴 분기 직후). 즉시 resume spawn은 worktree·PR 동시 mutation race를 일으키므로 spawn 분기 진입 전 probe 1회를 강제한다. 본 절차(정형·probe-ack·무응답 판정·분기 결정)는 §3-6 resume-probe의 공통 SSOT다 — 진입 조건과 `summary`/`reason` 어휘만 분기.

probe 정형 (5줄 이내, 산문 금지):

```
SendMessage(
  to: "{T}",
  summary: "stuck-probe {T}",
  message: "stuck-probe: {T}\nreason: <모순 A | 모순 B | 모순 C>\nevidence: <pr_state=MERGED/CLOSED | mergeStateStatus=DIRTY | mergeStateStatus=CLEAN pendingChecks=0 failedChecks=0 등 1줄>\nrequest: 현재 phase, 진행 blocker, ETA를 5줄로 회신"
)
```

**모순 E 전용 terminal-return-probe** (재emit 요청): `summary: "terminal-return-probe {T}"` + `reason: 모순 E` + `evidence: state.merged=<hash> 존재, 정규형 terminal 반환 미수신` + `request: process-ticket '서브에이전트 반환 형식 (강제)' 정규형을 SendMessage(to: "team-lead", summary: "terminal-return {T}")로 재emit`. 정규형 회신 수신 → §3-3과 동일 파싱 + drain 1회. 무응답(다음 enumerate 인터벌) → §3-6 fallback이 `state.merged`로 `wave_results` 보정 — 이 경우 `gaps_detected`/`gaps_dispatched` 회수 불가를 최종 리포트에 1줄 노출.

probe-ack 정형 (산문 금지): `probe-ack: {T}` / `phase: <현재 phase>` / `blocker: <1줄>` / `eta: <상태 전이 트리거 1줄 — wall-clock 금지>`.

무응답 판정: probe 발송 후 다음 enumerate 인터벌까지 응답 부재 — routine 자체 cadence와 일치, 새 임계값 도입 금지.

분기 결정:

- **응답 정상** (정형 충족 + ETA가 모순 해소 함의): spawn 생략, 다음 인터벌에서 state 전이 재확인. 동일 이슈 probe는 wave당 최대 3회.
- **응답 stuck 자인**: 의도 보강 메시지 1회 전송 → 다음 cycle에서 state 전이 없으면 spawn 분기.
- **무응답 (3 cycle 누적)**: resume spawn 분기.

### Resume 서브에이전트 spawn

stuck 확정 이슈를 §3-2-quater pool에 enqueue — 원본은 terminal 반환을 기다리지 않고 `superseded` 처리 + slot 회수. PR 식별자 + 마지막 known state를 prompt 인자로 명시하여 monitor 단계를 이어받게 한다:

```
Agent(
  subagent_type: "general-purpose",
  description: "resume {T}",
  run_in_background: true,
  permission_mode: "bypassPermissions",  # §3-2-ter 조건부 명시
  model: "sonnet",  # 상태 흡수형 resume(모순 A·C·E, terminal-return 회수) 한정 — 모순 B(conflict resolution)는 본 키 누락 (SKILL.md "규칙" 모델 티어링)
  prompt: "**FIRST TOOL CALL (deferred 스키마 선로드 — 단일 호출)**: 너의 맨 처음 tool 호출은 반드시 `ToolSearch(query: \"select:SendMessage,Skill\")` 하나여야 한다 — `Skill`·`SendMessage`는 deferred tool이라 첫 사용 시 스키마 지연 로드가 tool-definition prefix를 변이시켜 직전 prompt-cache를 무효화한다. spawn 직후 1회 `ToolSearch`로 두 스키마를 한꺼번에 선로드하여 prefix 변이를 spawn 시점 1회로 결정론적 고정한다. **FIRST ACTION (선로드 직후)**: Invoke the /process-ticket skill with argument '{T} --auto-merge'. **WORKTREE_ABS (메인이 §3-2-quinquies 재사용 확정)**: `{WORKTREE_ABS}` (branch `{BRANCH}`) — 원본 sub-agent의 워크트리와 `.process-state.json` 체크포인트를 그대로 이어받는다. `/create-worktree`·자체 `git worktree add` 호출 금지(hook 차단), 모든 git/파일 도구는 `worktree-isolation.md` §2 패턴. state: pr_opened={pr.number}, monitor_started={ts}, phase7_ready={phase7_ready|null}, merged=null. PR `#{pr.number}`가 {모순 사유}로 stuck — monitor 단계를 이어받아 처리(필요 시 clean terminal이면 Phase 8 auto-merge부터 즉시 진행, DIRTY이면 conflict resolution 후 재push)하고 정규형으로 반환하라. **Phase 6 monitor**: `monitor-pr/SKILL.md` §'절대 명령' + `process-ticket/phases/phase-6-monitor.md` 계약을 의역·완화 없이 적용 — 요약본 없음, binding (monitor-start ping·heartbeat ping·금지 어휘·turn 종료 자가검사 포함). `DONE reason=mergeable-clean` 또는 기존 `phase7_ready`는 반환 사유가 아니라 Phase 8 진입 조건이다. `phase7_ready`만 기록하고 반환하지 말고 같은 turn에서 `gh pr merge --squash --delete-branch`와 cleanup까지 완료하라. **commit/push 검증 ping**: process-ticket SKILL.md 정형 의무. **반환 형식**: §3-2와 동일 — terminal 반환 `SendMessage` emit 후에만 idle."
)
```

resume 반환은 §3-3과 동일 파싱 + drain 1회. **stuck 검출 → resume spawn → 반환** 사이클은 동일 이슈당 1회 제한 (무한 루프 방지) — resume도 stuck하면 §3-6 fallback 또는 charter §4-A 질의로 escalate.

알림 (wave당 최대 1회 집계): `[autopilot {N_done}/{M} ({P}%) ETA {Xh Ym}] wave[{w}] stuck 감지: {n_stuck}개 이슈 resume 서브에이전트 spawn ({tickets})` (`N_done` = 진행률 완료 수, `n_stuck` = 본 라운드 감지 건수).

stuck 미관찰 wave에서는 비활성(모순 0건 → spawn 0건) — 정상 경로 동작 불변.

## 3-3-ter. 외부 봇 위반 카테고리 누적 (durable ledger) — 조건부 Read

wave 내 PR **머지 이벤트 발생 시** `phases/ledger-bot-violations.md`를 Read하여 적용한다 — 머지 PR의 외부 봇 리뷰 코멘트를 durable ledger에 카테고리 누적(§3.6-1 S6 시그널 입력). 머지 0건 wave에서는 로드하지 않는다.

## 3-3-quater. ask-delegate 메시지 처리

sub-agent `ask-delegate` 수신 시 분기 본문(self_check Yes/No 판정 + 직렬 처리)은 process-ticket SKILL.md "사용자 질의 위임 → 메인 처리 분기" SSOT를 그대로 따른다 — 본 절은 분기 정의를 중복하지 않는다.

### gap-defer 회피 1차 판정 (self_check에 선행)

수신 즉시 그 질의가 즉시-분해 default(`behavioral-guidelines.md` "스펙 검증 / 후속 이슈")를 사용자에게 재확인하는 회피인지 판정한다. 다음 시그널 1개+ 매치 AND charter §4-A 진짜 트리거(스펙↔코드 직접 충돌·도메인 사전 미등록 신규 어휘·이슈 분해 단위 재정의의 비즈니스 의도 공백·destructive mutation 승인) 미동반이면 회피로 분류 — 진짜 트리거 동반 시 회피로 분류하지 않고 self_check로 넘긴다 (§4-A 경계 약화 금지):

1. 후속 이슈 생성 여부 자체를 묻는 질의 — "후속 이슈를 만들까요" / "분해해도 될까요" / "별도 PR로 빼도 될까요" / "지금 처리 vs 다음 wave" / "이번 PR 포함 vs 분리" 류.
2. 인지된 gap을 처리 권한 위임으로 표현 — "사용자가 결정할 사안" / "정책 결정 필요" / "운영 결정" / "스코프 결정" 류 라벨로 분해 default 우회.
3. 시간 이동 어법 — "다음에 볼 것" / "backlog" / "TODO" / "punt" / "추후 분리" / "별도 후속" / "우선은 보고만" 류 (question·options·notes 어디든).

회피 분류 시 `사용자 질의` 호출을 차단하고 sub-agent에 즉시 회신:

```
ask-resolution: <이슈 번호>
question: <원 질문 1줄 echo>
choice: gap-defer-rejected-apply-default
notes: behavioral-guidelines.md "스펙 검증 / 후속 이슈" 즉시-분해 default 적용. 본 ask-delegate는 gap-defer 회피로 분류되었음. 후속 이슈를 직접 생성하여 `spawned`·`gaps_dispatched`에 매핑할 것.
```

sub-agent는 수신 즉시 `/plan-issues`로 후속 이슈를 생성하고 turn 재개. 알림 1줄: `[autopilot ...] wave[{w}] ask-delegate gap-defer 차단: {T} → 즉시-분해 default 적용 회신`.

회피 아님 → process-ticket SKILL.md "메인 처리 분기" 그대로 진행. wave 중 언제든 처리 가능 — 메인 turn의 `사용자 질의`은 background sub-agent 진행을 방해하지 않는다.

## 3-3-quinque. wave 반환 외부 검증 routine (자기 보고 ↔ 사실 어긋남 차단)

`status: merged` 보고도 사실과 어긋날 수 있다(GitHub 미Done·본문 명세 일부 누락 머지). wave 반환 파싱 직후 메인이 직접 외부 검증한다. 적용 대상: 검증 1·2는 `merged` 한정 / 검증 3은 모든 terminal 반환(`merged`/`awaiting-review`/`failed`) — gap 보고 의무는 머지 여부와 무관 (charter §5 외부 게이트).

- **검증 1 (PR diff vs 수용 기준)**: `gh pr view <PR> --json body,files` 단발 조회 → PR 본문 "Acceptance Criteria (자가 grep)" 섹션(process-ticket Phase 4.5 첨부 — 비면 GitHub 본문에서 동일 규칙으로 추출) 회수 → 각 grep 라인을 머지된 develop tip에서 직접 실행하여 재검증. 미충족 1건+ → 어긋남.
- **검증 2 (GitHub status)**: `gh issue view 또는 GitHub connector 조회({ id: <T> })` 단발 조회 — `statusType != "completed"` → 어긋남.
- **검증 3 (gap-defer 차단)**: SSOT는 process-ticket "서브에이전트 반환 형식 (강제)" + `behavioral-guidelines.md` "gap 인지 = 즉시 분해 의무". 어긋남 조건: ① `gaps_detected`/`gaps_dispatched` 라인 부재 ② `gaps_detected != none` AND `gaps_dispatched == none` ③ 항목 수 ↔ 매핑 수 불일치 ④ `gaps_dispatched`의 ID가 `spawned`에 부재(분해 약속만 하고 미생성) ⑤ `gaps_dispatched`에 `ISSUE-NUMBER`·`in-pr` 외 어휘(`later`·`backlog`·`TODO`·`punt` 등 silent 미루기 어휘).

어긋남 시 분기:

- **검증 1·2**: §3.6-2 자동 이슈 생성 entry point를 그대로 호출 (신규 메커니즘 추가 금지) — 검증 1: `signal.name = "wave-return-acceptance-mismatch"` (evidence: 미충족 grep 라인 + PR URL + 머지 commit hash) / 검증 2: `signal.name = "wave-return-github-status-mismatch"` (evidence: `statusType` 실제값 + 이슈 URL). fix 이슈은 `meta_queue` 편입 (§3.6-2 큐 규칙). 검증 2는 fix 이슈과 별도로 즉시 `gh issue edit 또는 GitHub connector 갱신({ id: <T>, state: "Done" })` 강제 전이 + 재조회 보정 (process-ticket Phase 8 §3-bis 동일) — fix 이슈은 근본 원인 추적용, 보정은 즉시.
- **검증 3**: 자기 정정으로 회수 가능한 sub-agent 자기 판정 결함 — 메타 fix 이슈이 아니라 **같은 인자 재spawn**이 default: ① 원본 `superseded` + slot 회수 (머지·PR mutation은 유지, gap 보고 의무만 회수) ② 같은 인자(`{T} --auto-merge`) + "직전 반환의 위반 사유 1줄"을 prompt에 박아 re-dispatch (`run_in_background`·`permission_mode` 동일) ③ 동일 이슈 2회 연속 위반 → charter §4-A 질의 (`gap_defer_violation_count[T]` 이슈별 누적, 타 이슈과 합산 금지).

알림: 검증 1·2 어긋남 1건당 `[autopilot ...] wave[{w}] 외부 검증 어긋남: {T} {signal.name} → 메타 fix 이슈 {fix-id} 큐 편입` / 검증 3: `[autopilot ...] wave[{w}] gap-defer 차단: {T} → 재실행 (사유: {1줄})`.

§3-3-ter 봇 위반 누적과 직교 — 그쪽은 머지 후 외부 코멘트 패턴 누적, 본 routine은 자기 보고 어긋남 검출.

## 3-3-sex. 실행 중 sub-agent SendMessage 동반 — interrupt sentinel

팀메이트 메시지는 대상 turn 종료 시에만 배달된다 — Phase 6 monitor 루프는 DONE까지 turn을 끝내지 않으므로, 메인이 실행 중 sub-agent에게 보내는 모든 SendMessage(§3-3 intent-update / §3-3-bis stuck-probe·terminal-return-probe / §3-3-quater ask-resolution / §3-6 resume-probe)는 모니터링 종료까지 미배달될 수 있다.

**규칙**: SendMessage 송신 **직후** 그 sub-agent 워크트리 루트에 `.monitor-interrupt` 빈 파일을 쓴다 — `touch "{T 워크트리 절대경로}/.monitor-interrupt"`.

- **순서 고정**: SendMessage 먼저, sentinel 나중 — sentinel 감지 시점에 메시지가 이미 inbox 큐에 있어야 turn 종료 시 배달이 보장된다.
- 경로는 §3-3-bis enumerate 또는 spawn 시점 보유 절대경로 재사용 — 별도 추적 상태 금지.
- 소비: `watch.sh`가 매초 sentinel 확인, 삭제 후 `EVENT reason=interrupt` 즉시 반환 — sub-agent turn 종료 시 메시지가 배달되어 새 turn으로 재개 (소비자 측 SSOT: `monitor-pr/SKILL.md` §"Interrupt — 능동 지시 yield").
- Phase 6 밖이어도 안전: stale sentinel은 Phase 6 첫 watch.sh 전 하드클리어(`process-ticket/phases/phase-6-monitor.md`), monitor 미도달 시 워크트리 sweep이 제거 — 사전 phase 판별 없이 **모든 실행 중 sub-agent SendMessage에 일률 동반**한다.

## 3-3-septies. review-delegate 메시지 처리 (격리 리뷰 외부 게이트 복원)

sub-agent는 teammate 컨텍스트라 `Agent` tool이 없어 Phase 4 `/review-code`를 격리 spawn할 수 없고, in-context 수행은 charter §5 외부 게이트를 무력화한다 — `review-delegate` 위임(process-ticket SKILL.md "리뷰 위임 (sub-agent 한정)" SSOT)을 메인이 본 절차로 복원한다:

1. 메시지에서 `worktree`·`diff_range`·`issue_context`·`iteration`·`harness_ticket` 파싱.
2. **리뷰 컨텍스트를 메인 turn에서 1회 조립한다 (리뷰어 Read fan-out 제거).** 메인이 `review-code/SKILL.md` "운영 모델"의 컨텍스트 소스 — `personas/_common.md` + persona 5개(`architecture.md`·`type.md`·`naming.md`·`simplicity.md`·`test-coverage.md`) + 그 persona들이 인용하는 `rules/<file>.md` 본문 전량 — 을 Read하여 spawn prompt에 **본문 그대로 인라인**한다. `git -C <worktree> diff <diff_range>` 출력도 함께 인라인한다. 리뷰어는 이 인라인 본문을 14-카테고리 체크리스트로 직접 사용하며, persona·rules·diff를 다시 Read하지 않는다 — 누적 컨텍스트 재과금이 메인 turn 1회 Read로 수렴한다.
3. 격리 `general-purpose` 서브에이전트(`model: opus` — **불변**) spawn — §3-2 wave spawn과 별개, `team_name`/`run_in_background` 미발급(메인 turn 안 단발 회수), `permission_mode`는 §3-2-ter. prompt: 위 인라인 컨텍스트(_common+persona+인용 rules 본문+diff+`issue_context`)를 동봉하여 `/review-code`를 수행시킨다. **검출 의미론 불변**: 14-카테고리 전수 순회·Critical-0 수렴·각 카테고리 "통과 vs 미체크" 명시는 인라인 전달로도 동일하게 강제한다 — 인라인은 컨텍스트 **전달 방식**만 바꾸고 검출 범위·게이트는 무변. **카테고리·persona 선별 로드 금지**: diff에 관련 없어 보인다는 판단으로 persona나 rules 본문을 일부만 인라인하면 charter §5 self-confirmation bias가 부활하므로, 위 소스 전량을 항상 인라인한다. `harness_issue: yes`면 `/evaluate-harness`도 병행시킨다.
4. **결정론 0매치 카테고리 단락 (bias 부활 아님)**: diff 파일 글롭이 결정론적으로 0매치인 카테고리에 한해 파일 경로 기반 "통과(해당 파일 없음)"로 단락할 수 있다 — REST 컨벤션은 `adapters/apis/` 파일이 diff에 없을 때, 영속성/MongoDB 규율은 `models/`·repository 파일이 diff에 없을 때. 이는 LLM 판단이 아니라 파일 경로 매치의 결정론 판정이므로 §3 self-confirmation bias 금지와 직교한다. 글롭이 1개라도 매치하면 해당 카테고리는 전수 순회 대상으로 복귀한다.
5. 반환을 `review-result` 정형(process-ticket SKILL.md "리뷰 위임")으로 변환하여 `SendMessage(to: "{T}", summary: "review-result {T}")` 회신 — `iteration` 그대로 echo. 송신 sub-agent는 idle 상태이므로 회신만으로 새 turn 재개, sentinel 불요 (§3-3-sex는 watch.sh 점유 turn 전용 — Phase 4 리뷰 대기는 소비 주체 부재).

복수 동시 수신은 도착순 직렬 처리. 리뷰 spawn은 §3-2-quater pool `concurrency_limit`와 별개 — 메인 turn 안에서 완료되어 drain slot을 점유하지 않는다. 알림 1건당: `[autopilot ...] wave[{w}] review-delegate: {T} iter {N} → 격리 리뷰어 spawn`. §3-3-quater와 직교 — ask는 사용자 결정 질의 위임, review는 외부 게이트 위임(사용자 개입 없음).

## 3-3-octies. 메인 세션 신규 이슈 생성·편입 — 조건부 Read

메인이 신규 follow-up 이슈를 만들어야 하거나(plan-issues sub-agent spawn), `plan-issues-complete` 회신·사용자 직접 생성 이슈를 wave에 편입해야 하는 **이벤트 발생 시** `phases/new-ticket-intake.md`를 Read하여 적용한다 — plan-issues 경유 의무(§3-3-octies-1)·"하면서 편입" sub-agent 보존(§3-3-octies-2)·plan-issues-complete 단일 entry point(§3-3-octies-3) SSOT.

## 3-4. 실패 전파

웨이브 내 이슈이 `failed` 또는 `awaiting-review`(사람 응답 대기)이면, 그 이슈를 `blockedBy`로 가지는 **후속 웨이브 이슈(전이적 포함)**을 `skipped`로 표시한다 (`A→B→C`에서 A 차단 시 B·C 모두 skip — 차단 집합에서 BFS). 독립 가지는 계속 진행.

## 3-5. 다음 웨이브

모든 서브에이전트가 반환한 뒤 `w := w + 1`. 모든 웨이브가 끝나면 Phase 3.5로 진행.

## 3-6. 서브에이전트 비정상 종료 fallback (`.process-state.json` 회수)

서브에이전트가 monitor 도달 전 종료(반환 형식 위반·mid-thought 종료·context 소진 등 status 누락)해도 메인이 직접 추론으로 진행 상태를 메우지 않는다 — 워크트리 루트 `.process-state.json`(process-ticket SKILL.md "상태 핸드오프")을 읽어 resume 지점을 결정한다.

### SendMessage probe (공통 절차 = §3-3-bis)

spawn 분기 진입 전 §3-3-bis "SendMessage probe" 공통 절차(정형·probe-ack·무응답 판정·분기 결정)를 그대로 적용한다. 진입 조건 분기: `summary: "resume-probe {T}"`, `reason: 반환 형식 위반 또는 빈 결과`, `evidence: <pr_opened.number=N | merged 부재>`. 추가 분기:

- 정규 반환 형식 회신 → wave_results 적용, spawn 생략.
- 진행 의사 회신(정규 반환 미발생) → "wave 반환 형식 강제" 의도 보강 1회 → 다음 enumerate cycle까지 대기 → state 전이/정규 반환 도착 시 적용.
- 명시적 종료 자인(`terminated: <reason>` 회신) → 즉시 resume spawn 분기.
- 무응답(다음 cycle) → 아래 resume 분기. 메인 watch.sh 떠맡기 금지 — SKILL.md "규칙"(메인 직접 polling 금지 + monitor 전 종료 시 resume spawn) 정합.

```
worktree=$(ls -d <repo-root>/.claude/worktrees/<branch>)
state=$(cat "$worktree/.process-state.json" 2>/dev/null || echo "{}")
```

resume 분기:

1. `state.merged` 존재 → `wave_results[issue] = merged` 누적 후 진행 (반환 직전에만 죽은 케이스).
2. `state.pr_opened.number` 존재 + `merged` 부재 → §3-3-bis resume 템플릿 동일 형식으로 §3-2-quater pool enqueue (PR 식별자·마지막 known state 명시). 기존 워크트리 재사용 — drain 직전 §3-2-quinquies "존재 + resume/fallback" 분기 적용.
3. `state.pr_opened` 부재 → Phase 5 도달 전 종료. `status=failed`, `failed_reason=process-ticket terminated before PR creation` 기록 + §3-4 전파. 또는 같은 wave 1회 한정 재spawn(§3-2-quater pool + §3-2-quinquies 선생성) — 2회 연속 실패 시 질의.
4. `state.failed` 존재 → `status=failed`, `failed_reason=state.failed.reason` 기록.

`.process-state.json` 자체 부재(워크트리 진입 전 종료) → 동일 이슈 1회 재spawn, 2회 연속 부재 시 질의.

알림 (wave당 최대 1회 집계): `[autopilot ...] wave[{w}] fallback: {fallback_count}개 이슈이 process-state로 회수됨 ({merged_via_state}/{probed_resumed}/{re_dispatched})`.
