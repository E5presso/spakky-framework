---
name: process-ticket
description: GitHub Issue 번호를 받아 이슈 분석 → 구현 계획 → 워크트리 생성 → 구현 → 검증 → PR 생성 → CI/리뷰 모니터링 → 병합까지 전체 개발 사이클을 자동화합니다.
argument-hint: "<issue-number>"
user-invocable: true
---

# Process Ticket — 이슈 기반 자동 개발 사이클

GitHub Issue 번호 하나를 받아 이슈 분석부터 PR 병합까지 전체 개발 사이클을 오케스트레이션한다.

## 본질

`--auto-merge` 모드를 제외하면, 본 스킬의 산출물은 **PR이라는 폼팩터를 통해 사용자와 의사소통**하는 매체다. 코드 변경은 PR 본문·diff·코멘트·리뷰 스레드로 표현되고, 사용자의 결정 질의·반응·재지시도 같은 폼팩터 안에서 이루어진다.

본 스킬은 charter §4-B (구현 단계 = autonomous / positive bias)에 따라 **자동화 워크플로의 가치 = 인간 개입 최소화**를 핵심 가치로 보호한다. 저수준 기술 디테일 결정은 자율 진행이 default이며, 인간 게이트는 critical/policy-level 트리거에 한정한다.

따라서:
- **자율 진행 default**: 변수명·시그니처·헬퍼·테스트 위치·DI 형태 등 코드·도메인 사전·스펙 본문에서 도출 가능한 모든 결정은 묻지 않고 진행. 비자명한 결정은 PR 본문/커밋에 근거 1줄로 남겨 사용자가 PR 폼팩터에서 회수.
- **사용자 질의 트리거 (이것만)**: 머지 실행, charter §1 명백한 어긋남(이슈 어휘 ↔ 코드/사전 충돌), 도메인 사전 미등록 신규 어휘 도입, 이슈 분해 단위 재정의 필요, 정책·규칙 위반 가능성, 외부 시스템 destructive action.
- **금지된 질의 패턴**:
  - 별도 채널(`AskUserQuestion` 등)로 PR 폼팩터를 우회하여 저수준 디테일을 묻는 행위 — 자동화 가치를 무너뜨리는 회피 경로.
  - **sub-agent로 실행 중일 때 직접 `AskUserQuestion` 호출** — autopilot이 wave spawn 시 `Agent` tool의 격리된 컨텍스트에 들어가 있으므로, sub-agent의 직접 질의는 사용자가 autopilot 메인 turn 외부의 sub-agent turn으로 분리된 user-facing 채널을 강제로 열게 한다. autopilot은 N개 sub-agent를 동시에 spawn하므로 N개 직접 질의가 동시에 쏟아지면 user-facing ledger가 단일성을 잃는다. 대신 sub-agent는 SendMessage로 메인(team-lead)에 `ask-delegate`로 질의를 위임한다 (본 SKILL.md "사용자 질의 위임" 절 SSOT). 메인이 사용자 질의의 단일 채널이 된다.
- 리뷰 코멘트는 사용자/리뷰어가 PR 폼팩터로 보낸 결정 질의 그 자체이므로 자체 판단으로 처리한다 (`review-pr` SKILL 본문 참조).

## 비즈니스 의도 우선

`charter.md` §1을 모든 Phase 전체에 선행 적용한다. Phase 1 직후, Phase 2 진입 전에 charter §2 (3-축 정렬) 3가지(마일스톤 의도 / 티켓 위치 / 도메인 사전 정합)를 목적 어휘로 스스로 답하고 사용자에게 2-3줄로 **비차단 1-way 공유**한다 (charter §5 구현 단계 자율). 회신 대기 없이 즉시 Phase 2 진입.

**차단 조건 (이것만)**: charter §2 3-축 정렬에서 **명백한 충돌**(이슈 어휘 ↔ 코드/사전 어긋남, 산출물 중복, 정책 정면 충돌)이 관찰되면 즉시 차단하고 사용자 판정 질의. 그 외의 의도 모호성은 plan 단계(`/plan-issues`)에서 해소되었어야 하며, 본 스킬에서는 비차단 공유로 충분.

## 사용법

```
/process-ticket 42
/process-ticket 42 --require-approval
/process-ticket 42 --overnight
/process-ticket 42 --auto-merge
```

인자:
- **필수**: GitHub Issue 번호 (예: `42`, `#42`)
- **옵션**: `--require-approval` — 구현 계획에 대한 사용자 승인(Phase 2)을 요구한다. 기본값은 승인 없이 즉시 구현을 시작한다. PR 병합 승인(Phase 7)은 항상 필요하다.
- **옵션**: `--overnight` — 무인 실행 모드. Phase 2 계획 승인을 항상 생략하고, Phase 6 리뷰 코멘트 처리 시 **본인(PR 작성자) 코멘트만** `/review-pr`로 자동 처리한다. 타인 코멘트는 큐에 쌓아 대기하고 Phase 7에서 보고한다. Phase 7 병합 승인은 여전히 수동이며, overnight 모드에서는 "병합 대기" 상태로 **즉시 반환**(병합하지 않음 → Phase 8 생략). `--require-approval`과 동시 지정 시 `--overnight`가 우선한다.
- **옵션**: `--auto-merge` — 사용자가 사전에 병합을 승인한 자명한 이슈에 사용. Phase 7의 `AskUserQuestion` 병합 승인 단계를 생략하고 PR이 mergeable 상태가 되면 즉시 squash merge 후 Phase 8을 진행한다. CI/리뷰 게이트는 정상 적용되며, mergeable이 아니면 일반 모드와 동일하게 Phase 6으로 복귀한다. `--overnight`와 동시 지정 시 `--auto-merge`가 우선한다(병합 수행).

---

## Phase 개요

각 Phase 진입 시 해당 파일을 Read로 로드하여 단계별 절차를 적용한다.

## Phase 0: 사전 격리 가드 (필수 선행)

Phase 1 진입 직전에 메인 컨텍스트에서 **루트 리포지토리 HEAD가 develop 브랜치인지** 확인한다 (`git -C <repo-root> rev-parse --abbrev-ref HEAD`). develop이 아니면 다른 세션 / 형제 서브에이전트가 루트 리포지토리를 점유 중일 가능성이 있으므로 **즉시 시작 거부**하고 사용자에게 현재 브랜치명과 함께 보고한다. fallback 진행 금지 — 이 상태에서 Phase 3 워크트리 생성을 시도하면 형제 작업과 브랜치 충돌이 발생한다.

서브에이전트로 실행되어 cwd가 이미 루트 리포지토리에 묶여 있는 경우(`EnterWorktree`가 "already isolated" 오류를 반환하는 경우)에도 동일하게 가드한다. 이때는 `git worktree add .claude/worktrees/<branch> -b <branch> origin/develop`로 격리 워크트리를 명시적으로 만든 뒤 모든 후속 mutation을 워크트리 절대경로 안에서만 수행한다.

## Phase 1: 이슈 분석 + Phase 1.5: Blocker 확인 & 대기

GitHub Issue 본문/코멘트/상위 맥락 수집 → 작업 명세 정리 → blocker가 있으면 백그라운드 polling으로 완료 대기.

**상세**: `phases/phase-1-analysis.md`

## Phase 2: 구현 계획 수립

코드베이스 교차대조 + 판단 불확실 지점 식별 → Plan agent(opus)로 계획 수립 → `--require-approval`인 경우 사용자 승인.

**상세**: `phases/phase-2-plan.md`

## Phase 3: 워크트리 생성

`/create-worktree {prefix} {ISSUE-NUMBER}` 서브스킬 실행 → `EnterWorktree` 확인 → `/update-project-status {ISSUE-NUMBER} "In Progress"` 명시적 호출.

**격리 실패 시 즉시 종료 (fallback 절대 금지)**: `/create-worktree`·`EnterWorktree`·`git worktree add` 중 하나라도 실패하면 Phase 4 진입을 거부하고 사용자에게 실패 사유를 보고한 뒤 종료한다. 루트 리포지토리에서 직접 코드를 수정하거나, 다른 형제 워크트리를 재사용하거나, 브랜치만 체크아웃하여 진행하는 우회 경로를 채택하지 않는다 — 동시 실행 중인 형제 서브에이전트의 변경과 섞이며 PR diff 오염·머지 충돌·root repo branch flip 회귀를 일으킨다.

**상세**: `phases/phase-3-worktree.md`

## Phase 4: 구현 & 합리적 동료 리뷰 루프

구현 에이전트(opus)와 `/review-code` 리뷰 에이전트(opus)가 **합리적 동료(reasonable peer)** 관계로 의문점 수용/반박/후속 이슈 위임 루프를 **최대 2 iteration** 돌려 Critical 0개 생성 + `/check` 통과까지 수렴. Warning은 실제 운영 해 가능성이 구체적으로 관찰될 때만 보고하며, Info 심각도는 생성하지 않는다.

**상세**: `phases/phase-4-review.md`

## Phase 4.5: 수용 기준 자가 grep 게이트 (commit 차단)

리뷰 루프 수렴 직후 + Phase 5(commit/push/PR) 진입 직전에 **이슈 본문의 "수용 기준" 섹션에 박힌 grep 라인을 워크트리에서 실제 실행**하여 모든 라인의 기대값 일치 여부를 검증한다. 미충족 1건 이상이면 Phase 5 진입 차단 — 서브에이전트는 미충족 항목을 추가 구현 후 본 게이트 재실행. 본 게이트는 `/review-code`가 잡지 못하는 결함(본문 흡수 요청 중 일부만 처리·삭제 대상 import 잔존 등)을 수용 기준 grep 라인의 기계적 실행으로 차단한다.

**상세**: `phases/phase-4_5-acceptance-grep.md`

## Phase 5: 커밋 & PR 생성

`/commit` → `git push -u origin HEAD` → `/create-pr {ISSUE-NUMBER}` → `/update-project-status {ISSUE-NUMBER} "In Review"` 명시적 호출. 자동 진행.

**상세**: `phases/phase-5-commit.md`

## Phase 6: CI & 리뷰 모니터링

`Skill(monitor-pr, args: "{PR_NUMBER}")` 호출. `--overnight` 모드는 본인 코멘트만 자동 triage, 타인 코멘트는 큐에 대기.

**상세**: `phases/phase-6-monitor.md`

## Phase 7: 병합 준비 완료

PR이 merge 가능 상태가 되면 `AskUserQuestion`으로 병합 승인 요청. `--overnight` 모드는 상태 요약 후 즉시 반환(Phase 8 생략).

**상세**: `phases/phase-7-merge-gate.md`

## Phase 8: 병합 & 정리

`gh pr merge --squash --delete-branch` → `/update-project-status {ISSUE-NUMBER} "Done"` + `gh issue close {N}` 명시적 호출 → `ExitWorktree` → develop pull → 완료 보고.

**상세**: `phases/phase-8-merge-cleanup.md`

---

## 상태 핸드오프 — `.process-state.json` 체크포인트

서브에이전트가 monitor 도달 전 비정상 종료하면 호출자(autopilot 또는 사용자)는 어디까지 진행됐는지 추론으로 메워야 한다. 본 스킬은 워크트리 루트(`<worktree>/.process-state.json`)에 phase 경계마다 단일 JSON 파일을 갱신하여 명시적 핸드오프 점을 둔다. 추론 대신 파일을 읽어 resume 지점을 결정한다.

### 갱신 시점·필드

phase 경계마다 호출자가 `jq` 또는 동등한 도구로 다음 키를 갱신한다 (`null`이 아닌 키만 갱신, 기존 값 보존):

| 갱신 시점 | 필드 | 값 |
|----------|------|-----|
| Phase 5 commit 직후 | `commit_done` | 커밋 hash (HEAD) |
| Phase 5 push 직후 | `push_done` | `refs/heads/<branch>` |
| Phase 5 PR 생성 직후 | `pr_opened` | `{ "number": N, "url": "..." }` |
| Phase 6 LISTENING 진입 시 | `monitor_started` | ISO-8601 timestamp |
| Phase 8 merge 직후 | `merged` | merge commit hash |
| Phase 8 cleanup 완료 시 | `cleaned` | `true` |
| 임의 phase 실패 시 | `failed` | `{ "phase": "<name>", "reason": "<1줄>" }` |

공통 메타 필드:

- `issue_number`: GitHub Issue 번호
- `worktree`: 워크트리 절대 경로
- `updated_at`: 마지막 갱신 ISO-8601 timestamp

파일이 없으면 Phase 3 워크트리 진입 직후 위 메타 필드만 채워 초기화한다.

### autopilot fallback

서브에이전트가 monitor 도달 전 종료하면 autopilot은 워크트리의 `.process-state.json`을 읽어:

- `merged` 필드 존재 → 이미 머지 완료, 다음 wave 진행.
- `pr_opened` 존재 + `merged` 부재 → autopilot이 PR 번호로 직접 monitor-pr polling/머지를 떠맡는다 (charter §5 "메인 블로커 회피 금지").
- `pr_opened` 부재 → 같은 이슈를 다시 spawn한다 (Phase 5 도달 전 종료).
- `failed` 존재 → reason을 최종 리포트의 실패 사유로 사용.

### `.gitignore`

`.process-state.json`은 워크트리별 진행 상태이며 commit 대상이 아니다. 루트 `.gitignore`에 등록한다.

---

## GitHub 이슈/프로젝트 상태 자동 전이 (강제)

**phase 경계마다 `/update-project-status`를 명시적으로 호출하며, 실패 시 silent 누락 금지.** 머지 완료 이슈가 `In Progress`/`Backlog`로 남으면 마일스톤 진척도·autopilot DAG 판정이 어긋난다.

### 전이 시점 (`.process-state.json` 체크포인트와 동일 phase 경계)

| 시점 | 전이 | 트리거 | 체크포인트 동조 |
|------|------|--------|----------------|
| Phase 3 워크트리 진입 직후 | → `In Progress` | `EnterWorktree` 성공 직후 | 메타 필드 초기화와 동일 위치 |
| Phase 5 PR 생성 직후 | → `In Review` | `gh pr create` 성공·PR 번호 확보 직후 | `pr_opened` 갱신과 동일 위치 |
| Phase 8 머지 완료 직후 | → `Done` + `gh issue close {N}` | `mergeStateStatus=MERGED` 또는 `gh pr merge` exit 0 | `merged` 갱신과 동일 위치 |

각 phase 본문(`phases/phase-3-worktree.md`, `phase-5-commit.md`, `phase-8-merge-cleanup.md`)에 호출 코드가 박혀 있다 — "암묵적으로 알아서 한다" 금지.

### 실패 시 보고 (silent 누락 금지)

`/update-project-status` 서브에이전트 실행 결과를 호출자가 stdout으로 회수한다. 실행이 실패했거나 (비정상 exit, gh API 에러, 매칭 상태 부재 등) 스킬이 "갱신 실패" 경고를 출력했으면:

1. 메인 컨텍스트 stdout에 1줄 즉시 기록: `project-status-update-failed: <전이 명> <원인 요약>`.
2. 본 스킬 종료 시 반환 형식의 `notes:` 라인에 `project-status-update-failed: <전이 명> <원인>` 형태로 누락 사실을 노출하여 autopilot이 후속 보정할 수 있도록 한다 (`status: failed` 트리거가 아님 — process-ticket 본 작업은 계속 진행).
3. 본 작업(코드 변경·PR·머지)은 차단하지 않는다 — `/update-project-status` 자체가 호출자의 흐름을 차단하지 않는 정책이며, 본 스킬은 누락 가시성만 강제한다.

---

## Phase 전환 progress ping (sub-agent 한정)

본 스킬이 sub-agent로 호출된 경우, 각 Phase 진입 시점에 메인(team-lead)으로 SendMessage 1줄 ping을 보낸다. 메인 세션이 두 시점(머지 보고 SendMessage·idle_notification) 사이의 wall-clock 동안 sub-agent가 어느 phase에 있는지 보지 못하면 hang 의심 시 어디에서 막혔는지 진단할 수 없다 — phase ping 시계열이 사후 추적의 단일 입력이다.

### Ping 정형 (산문 금지, 1줄 강제)

`SendMessage(to: "team-lead", message: <ping>, summary: "phase-ping <issue>")` 의 message 본문 정형:

```
phase: <name> | issue: <N> | <1줄 요약>
```

- `<name>`: `Phase 1 analysis` | `Phase 2 plan` | `Phase 3 worktree` | `Phase 4 implement` | `Phase 4 review iter <N>` | `Phase 5 commit-pr` | `Phase 6 monitor` | `Phase 7 merge-gate` | `Phase 8 cleanup`.
- `<N>`: 이슈 번호 (예: `42`).
- `<1줄 요약>`: 해당 phase에서 곧 수행할 액션·관찰 사실 (예: `blocker none`, `PR #1234 opened`, `claude bot review iter 2`). 80자 이내.

본 ping은 단방향 — 메인 회신을 기다리지 않는다 (`ask-delegate`와 구별). sub-agent는 ping 송신 후 즉시 다음 액션 진행.

### 송신 시점 (phase 진입 직후 1회만)

| Phase | 송신 시점 | 요약 예시 |
|-------|-----------|-----------|
| Phase 1 | 이슈 fetch 직후 | `blockers <count>` 또는 `blocker none` |
| Phase 2 | plan agent spawn 직전 | `plan agent dispatched` |
| Phase 3 | EnterWorktree 직후 | `worktree entered` |
| Phase 4 | 구현 agent spawn 직전 | `impl dispatched` |
| Phase 4 review | 매 review iteration 진입 직후 | `iter <N> critical <count>` |
| Phase 5 | PR 생성 직후 | `PR #<N> opened` |
| Phase 6 | monitor 진입 직전 | `monitor armed` |
| Phase 7 | merge-gate 진입 직후 | `awaiting merge` 또는 `auto-merging` |
| Phase 8 | merge 직후 | `merged, sweeping` |

같은 phase 안에서 wall-clock이 길어지는 경우는 아래 "Phase 내부 heartbeat" + "Blocker 즉시 emit" 두 보강 규칙으로 가시성을 유지한다 — phase 전환 ping 자체는 회차마다만 송신한다. review iteration은 회차마다 별도 phase로 본다.

### Phase 내부 heartbeat (long-running 작업 가시성)

phase 전환 ping만으로는 phase 안에서 진행 중인 long-running 작업(통합 테스트 실행·CI polling·LLM 호출·다파일 grep·analysis loop)이 메인에 보이지 않는다 — 메인이 wall-clock 동안 sub-agent를 hang으로 오판할 수 있다. 다음 시점에 phase 내부 heartbeat ping을 1건 송신한다:

- 직전 ping(phase 전환 또는 직전 heartbeat) 송신 후 **3분 이상** 동일 phase에서 도구 호출이 누적된 경우
- 정형 (산문·여러 줄 금지):

  ```
  phase: <name> | tick: <action> | <1줄 상태>
  ```

  - `<name>`: phase 전환 ping과 동일한 명칭.
  - `<action>`: 진행 중 작업 어휘 (`integration-test`, `ci-polling`, `llm-eval`, `grep-scan` 등) — 1단어 또는 hyphen-joined.
  - `<1줄 상태>`: 현재까지의 관찰 사실 (예: `9 fails analyzing`, `wave 2/4 green`). 60자 이내.

heartbeat ping은 단방향 — 메인 회신 대기 금지. ping 1건당 메인 컨텍스트 비용 ≤ 100 토큰 (정형 강제로 자동 충족).

### Blocker 즉시 emit (phase 종료 대기 금지)

다음 시점에는 phase 종료를 기다리지 않고 발견 즉시 ping 1건 송신한다 — heartbeat 3분 주기와 무관하게 즉시 송신:

- CI red·CI fail 관찰
- 통합/유닛 테스트 fail 1건 이상 관찰
- triage decision 필요 (PR 코멘트 응답 보류·외부 mutation 사전 승인 필요)
- 환경 차단 (Docker 미기동·외부 API 401·서비스 unavailable)

정형 (`tick:` 자리에 `blocker:` 사용으로 heartbeat와 구분):

```
phase: <name> | blocker: <kind> | <1줄 상태>
```

- `<kind>`: `ci-fail` | `test-fail` | `triage-pending` | `env-block` 중 하나.
- `<1줄 상태>`: 차단 사실의 핵심 (예: `9 integration tests fail`, `mongo container down`). 60자 이내.

blocker ping은 ask-delegate(사용자 결정 질의)와 별개 — blocker ping은 단순 가시성, 결정 질의가 필요하면 별도로 ask-delegate를 추가 송신한다.

### 메인 세션 처리

메인은 phase 전환·heartbeat·blocker 세 종류 ping 모두 수신 시 텍스트 1줄로 사용자에게 즉시 표시하되 추가 액션을 취하지 않는다 — wave 진행 dashboard 갱신용. ping은 sub-agent의 회신·승인 요청이 아니므로 메인 turn을 차단하지 않는다. 누적 ledger만 갱신하여 사용자가 "어디서 멈춰있나" 질문 없이 마지막 ping으로 진행 위치를 식별할 수 있게 한다.

### 사용자 직접 호출은 적용 외

`/process-ticket` 직접 호출(메인이 곧 사용자 채널)에서는 송신하지 않는다 — 메인이 자기 자신에게 SendMessage하는 형태가 되어 의미가 없다. autopilot 등 sub-agent spawn 경로(team_name 발급)에서만 적용한다.

---

## 사용자 질의 위임 (sub-agent 한정)

본 스킬이 autopilot 등에 의해 sub-agent로 호출된 경우 (= spawn prompt에 `team_name`이 같이 발급된 경우), `AskUserQuestion` 직접 호출을 금지한다. 대신 SendMessage로 메인(team-lead)에 질의를 위임한다. 사용자 직접 호출(`/process-ticket 42`)인 경우 메인이 곧 사용자 채널이므로 본 inversion이 적용되지 않는다 — `AskUserQuestion` 직접 호출 그대로.

### 위임 메시지 정형 (`ask-delegate`)

`SendMessage(to: "team-lead", message: <ask-delegate>, summary: "ask-delegate <issue>")` 의 message 본문 정형 (산문 금지):

```
ask-delegate: <이슈 번호>
phase: <Phase 2-1 | Phase 4-2 | Phase 4-3 | Phase 7 | ...>
trigger: <charter §5 트리거 키워드 — 1줄>
question: <사용자에게 보일 질문 — 1줄>
options:
  - label: <옵션 1 라벨>
    description: <옵션 1 결과 1줄>
  - label: <옵션 2 라벨>
    description: <옵션 2 결과 1줄>
  ...
recommended: <옵션 라벨 또는 none>
self_check:
  a: <Yes/No — 본문/사전/하네스에서 도출 가능 1줄>
  b: <Yes/No — 권장안이 다른 옵션 대비 우월 1줄>
  c: <Yes/No — 채택 근거 1~2줄 가능>
```

`self_check`는 `behavioral-guidelines.md` "사용자 질문 방식" 자가검사 (a)/(b)/(c) 3개 결과를 sub-agent가 사전 작성하여 동봉한다 — 메인이 자가검사 결과를 보고 질의를 띄울지 결정한다.

### 메인 처리 분기 (본 절 SSOT — autopilot은 본 절을 인용한다)

1. **self_check 셋 다 Yes** → 권장안 즉시 채택 → 아래 `ask-resolution` 회신 (`choice: recommended-auto-applied`).
2. **self_check 한 항목 이상 No** → 메인이 `AskUserQuestion` 호출 (질문/옵션/배경 단락은 sub-agent가 보낸 본문 그대로 + No 사유 인용) → 사용자 회신 도착 → `ask-resolution` 회신 (`choice: <사용자 선택 라벨>`).

복수 sub-agent가 동시에 `ask-delegate`를 보내면 메인은 도착 순서대로 직렬 처리한다 — `AskUserQuestion` 카드는 한 번에 하나만 띄우고 회신 후 다음 카드로 넘어간다 (사용자 ledger 단일성 보장).

### 회신 메시지 정형 (`ask-resolution`)

`SendMessage(to: "<sub-agent-name>", message: <ask-resolution>, summary: "ask-resolution <issue>")`:

```
ask-resolution: <이슈 번호>
question: <원 질문 1줄 echo>
choice: <사용자가 선택한 옵션 라벨 | recommended-auto-applied>
notes: <사용자 자유 서술 또는 none>
```

sub-agent는 본 회신 수신 후 turn 재개. 회신 미도착 상태에서 sub-agent가 turn 종료하면 ledger 단일성이 깨지므로 sub-agent는 회신 대기 동안 turn 종료 금지 (메시지는 자동 delivery).

### 적용 phase 매핑

본 위임 패턴이 적용되는 sub-agent 질의 위치 (전 phase에서 `AskUserQuestion` 직접 호출 → `ask-delegate` 위임으로 inversion):

| Phase | 트리거 | 적용 |
|-------|--------|------|
| Phase 2-1 | charter §5 질의 트리거 (스펙↔코드 직접 충돌·도메인 사전 미등록 어휘·이슈 분해 단위 재정의·정책 위반) | sub-agent 한정 위임 |
| Phase 2-3 | `--require-approval` 시 plan 승인 | sub-agent 한정 위임 |
| Phase 4-2 | 직전 iteration 결정을 뒤집는 의문점 escalation | sub-agent 한정 위임 |
| Phase 4-3 | Default 모드 max iteration 초과 escalation | sub-agent 한정 위임 |
| Phase 7 | 정규 모드 머지 승인 (`--auto-merge`/`--overnight` 미지정) | sub-agent 한정 위임 |

## 서브에이전트 반환 형식 (강제)

본 스킬이 서브에이전트로 호출되어 종료할 때 반환 형식이 일정하지 않으면 autopilot의 다음 wave 진입 판정이 깨진다 (mid-thought 종료, status 누락). 본 스킬을 서브에이전트로 호출한 호출자(주로 autopilot)는 다음 형식만 수용한다 — 산문·진행 로그·중간 추론을 포함한 반환은 거부 후 재실행한다.

### 정규형 (산문 금지)

```
status: merged|awaiting-review|failed
pr: #N (URL) | none
issue: #N
acceptance_check: PASS|partial|missing
issue_status: Done|InReview|InProgress|Backlog|Cancelled
spawned: #N,...|none
failed_reason: 1줄 (status=failed 일 때만)
notes: 1줄 (비차단 누락·관찰 사실 — 옵션)
```

- `status`는 정확히 세 값 중 하나만. 부분 충족은 별도 status 값이 아니라 `acceptance_check: partial`로 표현하며, autopilot이 `status: merged + acceptance_check != PASS` 조합을 어긋남 시그널로 검출한다.
- `pr`은 `awaiting-review` / `merged`일 때 PR 번호 + URL을 포함한다. PR 생성 전 `failed`이면 `pr: none`.
- `acceptance_check`는 Phase 4.5 자가 grep 결과: 전 라인 기대값 일치 = `PASS`, 일부 라인 미충족 = `partial`, 이슈 본문에 grep 라인 자체가 없으면 `missing`. 본 스킬은 `partial` 또는 `missing`이면 `notes`에 미충족 grep 라인 1줄을 동봉한다. Phase 4.5 §3은 자가 grep FAIL 시 Phase 5 진입을 차단하므로 정상 경로의 `merged` 반환은 `acceptance_check: PASS` 또는 `missing`만 동반한다. `acceptance_check: partial`은 사용자 승인으로 부분 진행이 결정된 예외 경로(charter §5 질의로 사용자가 "부분 머지 후 후속 처리" 선택)에서만 발생한다.
- `issue_status`는 종료 시점에 `gh issue view {N} --json state,projectItems`로 **실제 조회한 GitHub 상태**(`closed` → `Done`, `open + Project Status` 매핑). 자기 보고와 사실의 어긋남 검출 입력 — `status: merged`인데 `issue_status: Done`이 아니면 호출자(autopilot)가 alert.
- `spawned`는 본 스킬 실행 중 charter §5 트리거나 후속 이슈 위임으로 생성한 신규 GitHub Issue 번호 목록 (없으면 `none`).
- `failed_reason`은 `status: failed`일 때만 추가하며, 1줄 (개행·코드블록 금지).
- `notes`는 본 작업을 차단하지 않는 누락·관찰 사실을 1줄로 노출할 때 사용한다 (예: `project-status-update-failed: In Review <원인>`, `acceptance-grep-missing: <line>`).

### 검증 정규식

호출자(autopilot)는 다음 정규식으로 1차 검증한다:

```
^status: (merged|awaiting-review|failed)$
^pr: (#\d+ \(https?://[^)]+\)|none)$
^issue: #\d+$
^acceptance_check: (PASS|partial|missing)$
^issue_status: (Done|InReview|InProgress|Backlog|Cancelled)$
^spawned: (#\d+(,#\d+)*|none)$
```

미준수 시 호출자는 본 스킬을 같은 인자로 재실행한다. 동일 이슈 2회 연속 형식 위반이면 charter §5 질의 트리거(기술적 모순)로 판단하여 사용자 질의.

---

## 권한 모드 inherit (sub-agent spawn)

본 스킬이 Plan agent·구현 agent·리뷰 agent 등 내부 sub-agent를 spawn할 때 (Phase 2-2 / Phase 4-1 / Phase 4-2 / Phase 4-5 등) `Agent({...})` 호출에 메인 세션의 권한 모드를 명시한다 — 메인이 bypass permissions 모드이면 sub-agent도 동일 모드로 진입시켜 도구 호출당 `permission_request` protocol 메시지가 메인 inbox로 송신되어 user-facing 채널이 시스템 트래픽으로 오염되는 것을 1차 차단한다. 메인이 bypass 모드일 때만 `permission_mode: "bypassPermissions"`를 명시하고, 일반 모드 메인은 키 자체를 누락한다. 본 스킬이 autopilot에서 sub-agent로 호출된 경우(`team_name` 발급)에는 autopilot 메인의 명시 정책이 이미 본 스킬 sub-agent에 적용되어 있으므로 별도 재적용 불필요 — 본 스킬 내부 spawn은 메인 세션의 모드를 다시 1회 평가하여 동일 키를 명시.

---

## 모델 티어링

Phase별 인지 난이도에 따라 서브에이전트/Plan agent를 서로 다른 모델로 실행하여 토큰을 절약한다. 메인 컨텍스트는 본 대화 세션의 기본 모델을 그대로 사용한다. 개별 서브에이전트 호출 시 `Agent(..., model: <tier>)`로 명시적으로 지정한다. **모델 미지정(부모 상속)은 금지** — 의도된 티어가 애매해진다.

| 단계 | 모델 | 근거 |
|------|------|------|
| Phase 1 이슈 분석 / 컨텍스트 수집 | `sonnet` | gh fetch + 요약 |
| Phase 2 구현 계획 수립 (Plan agent) | `opus` | 설계 판단 |
| Phase 3 워크트리 생성 (`/create-worktree`) | `haiku` | 결정론적 git 명령 시퀀스 |
| Phase 4 구현 루프 (코드 작성) | `opus` | 설계·구현 |
| Phase 4 검증 (`/check`) | `sonnet` | 명령 실행 + 로그 해석 |
| Phase 4 리뷰 (`/review-code`) | `opus` | 결함 탐지 판단 |
| Phase 5 커밋 메시지 / PR 본문 생성 | `sonnet` | 경량 글쓰기 판단 필요 |
| Phase 5 `git push` · `gh pr create` 실행 | `haiku` | 쉘 명령 집행 |
| Phase 6 `/monitor-pr` polling/상태 분기 | `haiku` | 결정론적 상태 머신. 판단(코멘트 수용/반론)은 `/review-pr`(`opus`)로 위임 |
| Phase 6 `/review-pr` 판단 | `opus` | 수용/반론 판단 |
| Phase 7 머지 게이트 상태 제시 | `haiku` | 상태 텍스트 포매팅 |

### haiku 허용 범위 가드레일

- **허용**: 결정론적 명령 시퀀스 실행, 상태 머신 분기, 고정 템플릿 채우기.
- **금지**: 코드 작성·설계·리뷰·판단(수용/반론, 재현 원인, 결함 탐지) — 최소 `sonnet` 이상. 판단이 개입하면 `haiku`를 쓰지 않는다.

---

## 임의 shell 명령 금지 (MUST)

본 스킬의 Phase 흐름은 **정의된 sub-skill / 정의된 도구 호출**만으로 진행한다. 메인 에이전트가 Phase 사이에 임의의 `gh ...`, `git ...`, `curl ...` 등을 끼워 넣으면 흐름이 흔들리고 동일한 검증을 반복하게 된다.

- **각 Phase는 정의된 진입점만 호출한다.**
  - Phase 1: `gh issue view`, `gh api repos/{owner}/{repo}/milestones/{N}` (이슈 + 마일스톤 + 선행/참조 이슈)
  - Phase 3: `/create-worktree`, `EnterWorktree`
  - Phase 4: `/check`, `/review-code`, `/plan-issues`
  - Phase 5: `/commit`, `/create-pr` — `git push -u origin HEAD`만 메인에서 직접 실행 허용
  - Phase 6: `/monitor-pr` (그 안에서만 polling/coment collect 실행)
  - Phase 6 분기: `/review-pr`
  - Phase 8: `gh pr merge`, `ExitWorktree`
- **PR 상태 확인은 `/monitor-pr` 결과만 사용한다.** 메인이 별도로 `gh pr view`, `gh pr checks`, `gh pr diff`를 호출하지 않는다.
- **PR 메타 mutation도 정의된 sub-skill을 거친다.** `gh pr edit`, `gh api ... replies` 등은 `/review-pr` 또는 `/create-pr` 안에서만 수행된다.
- **스크립트 출력이 부족해 보이면 스크립트를 수정한다.** 메인이 임의 명령으로 보강하지 않는다 — `/optimize-harness`로 진입.

## 규칙

- **사용자 확인 구간은 모드별로 다르다.** 기본: Phase 7 (PR 병합) 1곳. `--require-approval`: Phase 2 + Phase 7 두 곳. `--overnight`: 없음 (Phase 2 생략, Phase 7은 병합하지 않고 상태만 반환). `--auto-merge`: 없음 (Phase 7 승인 생략, mergeable 즉시 병합). 그 외 단계는 전부 자동 진행.
- 객관식 질문은 **반드시 `AskUserQuestion` UI** 사용. 텍스트로 질문하지 않는다.
- Phase 4 검증 루프는 생략하지 않는다. 단축키 없음.
- Phase 6 모니터링은 메인 컨텍스트에서 직접 실행한다 — 사용자에게 즉시 상태를 보고할 수 있어야 한다.
- Phase 6에서 리뷰 코멘트 처리 완료 후 해당 리뷰어에게 재리뷰를 요청한다.
- Phase 7에서 사용자 승인 없이 병합하지 않는다. `--overnight` 모드에서는 Phase 7이 **병합을 수행하지 않고 상태만 반환**하므로 이 규칙은 자동으로 지켜진다. `--auto-merge` 모드에서는 사용자가 옵션 지정 시점에 사전 승인한 것으로 간주하여 mergeable 상태가 되면 즉시 병합한다.
- **`--auto` (auto-merge) 절대 금지.** CI pending 등으로 즉시 병합이 불가능하면 사용자에게 보고하고 대기한다. `gh pr merge --auto`를 사용하지 않는다.
- **`--admin` 플래그 절대 금지.** CI/리뷰 보호 규칙을 우회하는 admin merge를 사용하지 않는다.
- 워크트리 환경에서 `.env`, `.env.local` 등 secrets가 필요하면 복사한다.
- 각 Phase 전환 시 사용자에게 현재 단계를 간결하게 알린다.
- **워크트리 필수 (구조적 강제)**: Phase 4~8의 모든 파일 mutation(코드 수정·커밋·PR 생성·체크아웃)은 반드시 워크트리 절대경로 안에서 수행한다. Read·Edit·Write·Bash 도구의 경로가 루트 리포지토리(`spakky-framework/` 직속) 또는 다른 이슈의 워크트리를 가리키는 즉시 중단 — `git worktree list`로 본 이슈 워크트리 경로를 재확인하여 모든 후속 호출에 그 절대경로를 사용한다. 워크트리 생성 실패 시 구현을 시작하지 않고 즉시 중단한다 (Phase 3 "격리 실패 시 즉시 종료" 참조). fallback으로 루트 리포지토리에서 진행하지 않는다.
- 서브 스킬 호출은 **서브에이전트**로 실행 — 비차단 스킬은 백그라운드, 결과 필요 스킬은 포그라운드.

$ARGUMENTS
