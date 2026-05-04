---
name: autopilot
description: GitHub 마일스톤 또는 부모 이슈를 받아 자식 티켓들을 DAG wave-loop로 병렬 처리합니다. 후속 티켓 즉시 spawn, 자기 운영 결함 자동 감지(meta-detection), 마일스톤 단일 세션 완성을 보증합니다.
argument-hint: "<milestone-number | parent-issue-number>"
user-invocable: true
---

# Autopilot — 마일스톤 SDLC 자동 오케스트레이션

`/process-ticket`을 단일 티켓 단위로 호출하는 대신, **마일스톤 또는 부모 이슈의 자식 티켓 전체**를 DAG wave-loop로 병렬 자동 처리한다. 후속 티켓이 발생하면 즉시 spawn, 자기 운영 결함은 자동 감지하여 별도 fix wave로 처리.

## 자동 병합 권한

`/autopilot` 호출 자체는 해당 마일스톤/부모/명시 티켓 집합의 clean PR에 대한 **사전 squash merge 승인**이다. Autopilot 메인은 티켓별 Phase 7 병합 승인 질문을 사용자에게 띄우지 않는다.

- wave spawn은 항상 `/process-ticket {T} --auto-merge`로 진입한다.
- PR이 `mergeStateStatus in (CLEAN, UNSTABLE)`이고 required checks/review bot HEAD 평가가 완료되면 process-ticket은 Phase 8로 즉시 진행한다.
- sub-agent가 실수로 `phase7_ready` 또는 `status: blocked`/`merge approval required` 형태로 반환하면 autopilot은 사용자에게 묻지 않고 resume sub-agent를 `--auto-merge`로 재기동한다. 같은 이슈에서 2회 반복되면 S1/S2 메타-감지로 하네스 fix 티켓을 생성한다.
- 사용자 질의는 스펙-코드 충돌, 외부 destructive action, 사람 리뷰 코멘트에 대한 제품 결정처럼 charter 질의 트리거가 있는 경우에만 가능하다. clean PR 병합 자체는 autopilot에서 질의 트리거가 아니다.

## 사용법

```bash
/autopilot 12              # 마일스톤 #12의 자식 이슈 전체
/autopilot parent:42       # 부모 이슈 #42의 자식 이슈 전체
/autopilot 7,8,9           # 명시적 이슈 목록
```

---

## Phase 1: 티켓 수집 (Dual-Path 수렴 게이트)

GitHub의 milestone 필터/parent 추적이 누락 가능성이 있다. 두 경로로 수집하여 **불일치 시 자동 fix 티켓 생성**.

### 1-1. Path A: GitHub API 페이지네이션

```bash
gh issue list --milestone {N} --state open --json number,title,body,labels,assignees --limit 100
```

### 1-2. Path B: 마일스톤 description 본문 파싱

마일스톤 description에서 명시된 자식 이슈 번호 (예: `Children: #7, #8, #9`) 추출.

### 1-3. 수렴 게이트

A와 B를 비교:
- 일치: 진행
- 불일치 (A에 있으나 B에 없음 등): **harness fix 티켓 자동 생성** (Phase 3.6 meta-detection 시그널) 후 사용자 보고. 진행 여부 사용자 확인.

## Phase 2: DAG 구성 & 위상정렬

각 티켓의 본문에서 `blockedBy: #N` 또는 `Depends on: #N` 표기를 파싱하여 의존 그래프 구성.

```
wave[0] = blocker 없는 티켓
wave[1] = wave[0]만 blocker로 가진 티켓
wave[2] = wave[0,1]만 blocker로 가진 티켓
...
```

순환 의존 감지 시 즉시 stop & 사용자 보고.

## Phase 3: Wave 실행 루프

```
for wave_idx, wave in enumerate(waves):
    skip = read_skip_set()  # 실패 전파로 skip된 티켓
    spawn_targets = [t for t in wave if t not in skip]

    # 3-2. 병렬 spawn (단일 메시지의 다중 Agent tool_use, /process-ticket --auto-merge)
    results = spawn_parallel(spawn_targets, run_in_background=True)

    # 3-3. 반환 대기 + 즉시 spawn (recursively)
    for r in results:
        if r.spawned:  # 후속 티켓 즉시 spawn (약속 차단)
            spawn_parallel(r.spawned, run_in_background=True)

    # 3-3-bis. Stuck 감지 (논리적 모순 기반, wall-clock 금지)
    if detect_stuck(results):
        report_and_pause()

    # 3-4. 실패 전파 (BFS로 후속 노드 skip)
    propagate_failures(results, downstream_waves)

    # 3-5. 다음 웨이브
```

### 3-3-bis. Stuck 감지 시그널 (모순 기반)

| 시그널 | 모순 정의 |
|-------|---------|
| monitor-stuck | PR mergeable + CI green인데 process-ticket이 Phase 7 진입 안 함 |
| merge-gate-stuck | autopilot 하위 process-ticket이 clean PR에서 병합 승인을 사용자에게 요청하거나 `phase7_ready` 상태로 반환 |
| state 부재 | 워크트리에 `.process-state.json` 없음 |
| state 역행 | phase 키 역행 (Phase 6 → Phase 4) |
| 동일 파일 mutation | 다른 워크트리들이 같은 파일을 동시 수정 |

**wall-clock timeout 절대 금지.** 시간이 오래 걸린다고 stuck이 아니다. 모순만이 stuck.

### 3-3-quinque. 후속 티켓 즉시 spawn

서브에이전트 결과의 `spawned: [...]` 필드를 **동일 turn 내 spawn**한다. "후속 티켓을 만들겠습니다"만 남기고 종료하는 것 원천 차단.

## Phase 3.5: 후속 티켓 회수 (Fallback Fixed-Point)

Phase 3-3-quinque에서 누락된 spawn이 있을 수 있다. Wave 종료 후:

```
M = compute_missing_spawns()  # 약속 vs 실제 spawn 차집합
while M != ∅:
    spawn_parallel(M, run_in_background=True)
    M = compute_missing_spawns()
    if same_M_repeats(threshold=3):
        report_cycle_and_stop()  # 순환 분해 의심
```

## Phase 3.6: 자기 운영 결함 메타-감지

전체 wave 수행 중 다음 시그널을 누적 ledger로 기록:

| 시그널 | 모순 정의 |
|-------|---------|
| S1 monitor-stuck | (3-3-bis와 동일) |
| S2 resume loop | 동일 ticket에 fallback resume 2회+ spawn |
| S3 직렬화 미작동 | 동일 파일 mutation PR 3개+ 동시 OPEN |
| S4 state 부재/역행 | (3-3-bis 항목) |
| S5 consumer 미감지 | EVENT 발생인데 phase 전이 부재 |
| S6 외부 봇 위반 누적 | 같은 카테고리 위반 3회+ ledger |
| S7 merge-gate-stuck | autopilot 하위 clean PR이 사용자 병합 승인 대기로 반환 |

매치 시 **기존 open harness fix 티켓을 먼저 재사용**하고, 없을 때만 신규 티켓을 생성한다. meta 시그널은 중복 생성이 아니라 수렴 대상 식별이 목적이다.

### 3.6-a. meta issue dedupe/reuse 게이트

`gh issue create` 전에 다음 순서로 open 이슈를 조회한다:

```bash
gh issue list --state open --search "repo:E5presso/spakky-framework S1 OR S7 OR monitor-stuck OR merge-gate-stuck" --json number,title,body,labels --limit 50
```

1. 동일 시그널 코드(S1-S7)와 동일 원인 어휘(예: `monitor-stuck`, `merge-gate-stuck`, `state 역행`)가 모두 매치되는 open 이슈가 있으면 **그 이슈 번호를 `meta_queue`에 추가**하고 새 이슈를 만들지 않는다.
2. 제목은 다르지만 본문이 같은 PR/issue evidence 집합을 포함하는 open 이슈가 있으면 duplicate로 보고 **기존 이슈를 재사용**한다.
3. 매치되는 open 이슈가 없을 때만 `gh issue create`를 실행한다.
4. 신규/재사용 어느 쪽이든 ledger에는 `signal`, `evidence`, `meta_issue`, `action: reused|created`를 기록한다.

재사용한 이슈가 현재 autopilot 실행의 마일스톤/부모에 연결되어 있지 않더라도, `meta_queue` 처리 대상에는 반드시 포함한다. 중복 open 이슈를 발견했지만 이미 같은 원인의 closed 이슈/merged PR이 있으면, 새 티켓을 만들지 말고 open leftover를 evidence와 함께 정리 대상으로 남긴다.

### 3.6-b. meta_queue 별도 wave

`meta_queue`는 일반 wave 실패 전파와 분리한다. 각 항목은 `/process-ticket {meta_issue} --auto-merge`로 처리하고, 처리 결과가 merged/closed가 될 때까지 Phase 3 fixed-point 루프로 복귀한다.

Ledger 위치: `~/.claude/projects/-Users-spakky-Documents-projects-spakky-framework/state/autopilot-ledger.json`

## Phase 4: 의도 감사 (Intent Audit)

전체 wave 종료 후, 마일스톤 description의 의도와 머지된 PR들의 합집합이 일치하는지 외부 서브에이전트로 감사. `/audit-codebase`와 같은 다관점 검증 위임.

발견된 갭 → 신규 자식 티켓 생성 후 Phase 3로 복귀 (fixed-point).

## Phase 5: 문서 동기화

`/sync-docs all`을 호출하여 머지된 코드 변경에 따른 문서 일괄 동기화.

## Phase 5.5: 최종 meta/open 이슈 fixed-point sweep

Phase 6 최종 보고 직전에, autopilot은 마일스톤/부모 범위와 ledger의 `meta_queue`가 모두 닫힌 고정점인지 확인한다. 이 sweep을 통과하기 전에는 마일스톤 완료/종료를 선언하지 않는다.

1. GitHub open 이슈를 다시 조회한다:

   ```bash
   gh issue list --state open --milestone {N} --json number,title,body,labels --limit 100
   gh issue list --state open --search "repo:E5presso/spakky-framework label:enhancement S1 OR S2 OR S3 OR S4 OR S5 OR S6 OR S7 OR meta_queue OR monitor-stuck OR merge-gate-stuck" --json number,title,body,labels --limit 100
   ```

2. ledger의 unresolved `meta_queue` 항목과 GitHub open meta issue 조회 결과를 합집합으로 계산한다.
3. 합집합이 비어 있으면 Phase 6으로 진행한다.
4. 합집합에 기존 open meta issue가 있으면 새 이슈를 만들지 않고 해당 이슈들을 `meta_queue`로 재주입하여 Phase 3으로 복귀한다.
5. 같은 open set이 3회 반복되면 순환/외부 blocker로 보고하고 stop한다. 이 경우에도 중복 이슈를 추가 생성하지 않는다.

## Phase 6: 최종 보고

```
## Autopilot 완료

마일스톤: #{N} ({title})
처리 티켓: {K}개 (성공 {S}, 실패 {F}, skip {SK})
spawned 후속 티켓: {N}개
meta_queue 처리: {M}개
사이클 시간: {hh:mm:ss}
```

---

## 규칙

- **단일 티켓은 `/process-ticket` 사용.** Autopilot은 마일스톤·부모 단위만.
- **wave 내 spawn은 단일 메시지의 다중 Agent tool_use.** 순차 spawn 금지 (메인 turn 점유 방지).
- **autopilot은 병합 승인 질문 금지.** `/autopilot` 호출이 clean PR squash merge 사전 승인이다. 하위 티켓은 `/process-ticket --auto-merge`로만 처리한다.
- **wall-clock timeout 절대 금지.** Stuck 감지는 논리적 모순 기반만.
- **후속 티켓 즉시 spawn 의무.** Phase 3-3-quinque 건너뛰기 금지.
- **Phase 3.6 meta-detection 시그널 매치 시 open 이슈 dedupe/reuse 후 meta_queue 처리.** 중복 harness fix 티켓 생성 금지.
- **최종 보고 전 Phase 5.5 meta/open 이슈 fixed-point sweep 필수.** open meta_queue가 남아 있으면 마일스톤 완료 선언 금지.
- 워크트리는 티켓별 분리. 동일 파일 mutation 충돌 시 직렬화 강제 (S3 시그널).
- Phase 4 의도 감사는 외부 서브에이전트만 (자기확증 편향 차단).

$ARGUMENTS
