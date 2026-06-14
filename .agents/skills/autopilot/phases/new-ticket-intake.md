# §3-3-octies. 메인 세션 신규 GitHub Issue 생성·편입 (단일 진입점)

> **로드 트리거**: 메인이 신규 follow-up 이슈 생성 필요 / `plan-issues-complete` 회신 수신 / 사용자 직접 생성 이슈 편입 시 Read (`phase-3-wave-loop.md` §3-3-octies).

메인의 `gh issue edit 또는 GitHub connector 갱신` 직접 create와 진행 중 sub-agent shutdown/cancel/pause 회피 경로를 외부 게이트로 차단한다. sub-agent의 자기 후속 분해(`spawned` 보고 → §3-3-quinque 즉시 spawn)와 직교 — 본 파일은 **메인 측 경로**만 다룬다.

**update 호출 공통 면제 (1회 선언)**: `id` 인자가 있는 `save_issue` **update** 호출(status 강제 전이, assignee/labels/relations/project/milestone 보정)은 본 § 전체의 금지 범위 외다 — 금지는 `id == null` **create** 한정. 단, update 경로를 가장해 `id` 필드 없는 create 슬롯을 추가하면 본 § 위반.

## 3-3-octies-1. 신규 create는 plan-issues sub-agent 경유 의무

- **금지 (default)**: 메인의 `gh issue edit 또는 GitHub connector 갱신({ id: null, ... })` 직접 create. 직접 create는 spec-first 분해(plan-issues Phase 2.5 SDD 스펙 artifact)·도메인 사전 검증(Phase 1 §6)·산출물 중복 검사(Phase 1 §7)·라벨/메타 표준화(Phase 4 self-check) 게이트를 전부 우회한다 — 모든 생성 이슈이 동일 품질 바를 통과한다는 보장이 깨진다.
- **우회 시 분류**: §3-3-quinque 검증 3(gap-defer 차단)과 동등한 자기 검증 위반 — 메인은 create 직후 같은 turn에서 자가검사하고, 매치 시 그 이슈를 `Canceled` 처리(§3-3-octies-2 보존 규칙은 sub-agent 한정 — 메인 자신의 잘못된 create는 본인 책임 cancel)한 뒤 plan-issues 경로로 재진입한다.
- **예외 enumeration (이 외 신규 create 금지)**: ① update 호출 (상단 공통 면제) ② sub-agent 자기 `spawned` 보고 경로 — sub-agent가 자기 turn에서 `/plan-issues`로 생성·보고한 ID는 메인이 `save_issue` 재호출 없이 metadata 검증 + spawn pool enqueue만 수행 (§3-3-quinque 분기).

## 3-3-octies-2. "하면서 편입" 원칙 — 진행 중 sub-agent 보존

**default**: (a) 사용자 mid-flight 정정·신규 방향성 (b) plan-issues 산출 신규 issue 편입 (c) 메타 fix 추가 — 어떤 외부 트리거로도 이미 spawn된 process-ticket sub-agent를 종료하지 않는다. 신규 issue는 §3-2-quater pool에 추가 enqueue하여 active slot이 비는 대로 병렬 spawn — 진행 중 wave 진척을 보존하면서 신규 작업을 추가한다.

**금지 행동 enumeration**: ① 진행 중 sub-agent에 `shutdown_request` 송신 ② `TaskStop`으로 background task 외부 종료 ③ `intent-update`를 가장한 "현재 작업 중단 + 다른 작업 전환" 지시 ④ wave abort 후 재시작 (워크트리·PR 상태 무효화).

**예외 enumeration (이 외 진행 중 종료 금지)**: ① §3-3-bis stuck 검출 후 `superseded` (probe 무응답 + state 모순 = 책무 종료 자인) ② §3-3-quinque 검증 3 재spawn의 `superseded` ③ §3-6 `state.pr_opened` 부재 케이스 1회 재spawn (원본 종료가 외부 신호로 확정됨).

예외 외 종료는 본 § 위반 — 메인은 다음 turn에서 자가검사하고 §3.6-2로 `signal.name = "in-flight-sub-agent-shutdown"` fix 이슈를 생성한다 (회귀 추적용).

## 3-3-octies-3. plan-issues-complete 회신 처리 — 단일 entry point

메인이 §3-3-octies-1 경로로 `/plan-issues` sub-agent를 spawn한 경우, `plan-issues-complete` 회신(산출 issue number 목록) 수신 직후 단일 단락으로 수행한다:

1. **metadata 검증**: 각 ID에 §3-3-quinque 메타데이터 계약 검증·보정 절차(`get_issue` 단발 조회 → 1회 `save_issue` update 보정 → 재조회)를 그대로 적용. 2차 재조회도 어긋나면 해당 ID를 `spawn_metadata_blocked`에 보관 + §3.6-2로 `signal.name = "plan-issues-output-metadata-mismatch"` fix 이슈 생성.
2. **enqueue**: 통과 ID를 §3-2-quater `pending_spawn_queue`에 추가 — §3-2-bis 동일 team 재사용, `name` = issue number, `run_in_background: true`, `permission_mode`는 §3-2-ter.
3. **drain**: active slot이 있으면 같은 turn에서 최대 5건 한도로 §3-2-quinquies 워크트리 선생성 → spawn까지 진행. slot 없으면 queue 대기, terminal 반환 1건당 다음 1건 (§3-3-octies-2 정합 — 진행 중 sub-agent 비종료).

본 회신이 wave list 편입의 단일 entry point — 회신 본문 ID를 다른 경로(직접 `save_issue` 재호출 + 직접 spawn)로 처리하는 것은 우회이며 본 절차를 따른다. 알림 1건당: `[autopilot ...] wave[{w}] plan-issues-complete 편입: {X1, X2, ...} active={active} queued={queued}`.

## 3-3-octies-4. 적용 외 경계

- **사용자가 직접 만든 issue**: §3-3-octies-1 적용 외 — 메인이 wave에 편입할 때만 §3-3-octies-3 metadata 검증 절차를 적용.
- **§3.6-2 메타 fix 이슈 생성**: §3-3-octies-1 **적용 대상** — plan-issues sub-agent 경유.
- §3-3-quater(ask-delegate — sub-agent 측 회피 차단, 메인이 `ask-resolution`으로 plan-issues 호출 지시)와 직교 — 두 경로 모두 plan-issues가 단일 issue 생성 진입점임을 강제한다.
