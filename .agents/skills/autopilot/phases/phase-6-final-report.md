# Phase 6: 최종 리포트

## 6-0. 부모 epic 자동 Done 처리 (강제 게이트 — 리포트 출력 직전)

Phase 5 sync-docs 종료 후 최종 리포트 출력 전에, 자식 이슈이 모두 머지된 부모 epic을 GitHub `Done`으로 일괄 마감한다. 자식 머지 결과는 이미 §3-3에서 `merged_children`에 누적되어 있고, 부모 ↔ 자식 매핑은 Phase 1 §3에서 `parent_epics`에 저장되어 있으므로 추가 외부 조회는 필요 없다.

**강제 게이트**: 본 단계는 Phase 6 최종 리포트 출력의 **선행 필수 단계**다. `parent_epics`가 비어 있더라도 본 단계 진입 사실 자체를 리포트에 노출(아래 §6-1 "부모 epic 자동 마감" 섹션에 `대상 부모 epic 0개 — 본 실행에서 식별된 epic 없음`)하여 외부에서 §6-0 실행 여부를 검증할 수 있게 한다. silent skip은 회귀를 발생시키므로, Phase 6 리포트 출력 직전 본 단계의 실행 흔적이 리포트에 포함되지 않으면 abort.

알고리즘:

```
auto_done_acc = []
auto_done_pending = []
for epic_id, children in parent_epics.items():
  if all(child in merged_children for child in children):
    try:
      gh issue edit 또는 GitHub connector 갱신({ id: epic_id, state: "Done" })
      # 호출 직후 상태 재조회 검증
      verify = gh issue view 또는 GitHub connector 조회({ id: epic_id })
      if verify.statusType == "completed":
        auto_done_acc.append(epic_id)
      else:
        auto_done_pending.append((epic_id, f"save_issue 호출 후 상태 재조회 = {verify.status} (Done 아님 — silent failure 의심)"))
    except Exception as e:
      auto_done_pending.append((epic_id, f"GitHub API 실패: {e}"))
  else:
    pending_children = [c for c in children if c not in merged_children]
    auto_done_pending.append((epic_id, f"자식 미완료 {len(pending_children)}개: {pending_children}"))
```

핵심 속성:

1. 외부 자식(대상 마일스톤 외)은 `parent_epics` 단계에서 이미 제외되었으므로 본 검증에 영향을 주지 않는다.
2. GitHub API 호출 실패는 charter §4-A 질의 트리거로 분류하지 않고 `auto_done_pending`에 사유 1줄과 함께 기록 — 사용자가 최종 리포트에서 수동 마감을 결정한다.
3. 자식이 비어 있는 부모는 Phase 1 §3 판정 기준상 부모 epic으로 식별되지 않으므로 `parent_epics`에 들어오지 않는다.
4. 자기 마감 절대 금지 — 본 단계는 부모 epic만 대상으로 하며, 본 autopilot 인자 자체(예: 마일스톤 트래킹 이슈)에 직접 적용되지 않는다.

## 6-0-bis. 잔존 워크트리 sweep (외부 안전망)

process-ticket Phase 8 cleanup이 어떤 사유로든 누락되어 머지된 PR의 워크트리·로컬 브랜치가 남는 케이스에 대비해, 본 단계가 wave 종료 시점의 외부 안전망으로 동작한다. process-ticket Phase 8이 정상 실행된 워크트리는 이미 제거되어 본 sweep의 후보가 아니므로 idempotent하다.

**스코프 한정 (MUST)**: 본 sweep의 선언된 의도는 "본 autopilot이 머지한 PR의 잔존 워크트리"를 정리하는 것이다 — 리포지토리 전역의 머지된 워크트리가 아니다. `git worktree list`는 본 autopilot이 만들지 않은 다른 세션·작업의 워크트리까지 전부 enumerate하므로, 그 결과를 그대로 `worktree remove --force` 대상에 넣으면 진행 중인 다른 세션의 작업 디렉토리·미커밋 변경을 파괴한다. 따라서 enumerate 결과를 **본 autopilot 실행이 소유한 이슈 번호 집합**에서 파생된 워크트리로 필터한 뒤에만 머지 판정·제거를 적용한다. 소유 집합은 실행 상태 사전에서 직접 도출한다:

```
owned_issues = set(issue_metadata_by_id.keys()) | spawned_dispatched | meta_queue
```

- `issue_metadata_by_id.keys()` — Phase 1 §3-bis가 부모 epic 제외 후 남긴 대상 이슈 집합.
- `spawned_dispatched` — Phase 3 §3-3-quinque가 즉시 분해하여 spawn한 후속 이슈 집합.
- `meta_queue` — Phase 3.6 §3.6-2 / §3-3-quinque 검증이 만든 메타 fix 이슈 집합.

워크트리의 소속 이슈은 브랜치명 prefix를 `^([A-Z]+-[0-9]+)` (대소문자 무시 — 브랜치명은 `feat/1545`·`feat/1686` 양형으로 나타난다)로 파싱하여 도출한다. 파싱한 이슈 번호가 `owned_issues`에 없으면 그 워크트리는 본 autopilot의 대상이 아니므로 sweep 후보에서 제외한다 (§3-3-bis가 stuck 감지에서 쓰는 branch name parse와 동일 규칙).

**sweep 명령은 rtk 프록시를 경유하지 않는다 (MUST).** 본 sweep의 `git worktree list`·`grep`·`awk` 출력은 워크트리 제거 판정의 입력이므로, rtk 프록시의 출력 압축·truncate가 한 줄이라도 변형하면 소속 이슈 파싱·머지 판정이 오판되어 다른 세션의 워크트리를 잘못 제거하거나 본 autopilot의 워크트리를 누락할 수 있다. 본 코드 블록의 모든 명령은 `rtk proxy <cmd>` 형식(raw 실행)으로 호출하여 출력 원형을 보존한다.

알고리즘:

```bash
# 0. 본 autopilot 실행이 소유한 이슈 번호 집합 (대문자 정규화)
#    owned_issues = issue_metadata_by_id.keys() | spawned_dispatched | meta_queue
#    실행 상태 사전에서 도출한 ID들을 줄당 1개로 기록한다.
printf '%s\n' "${OWNED_ISSUES[@]}" | tr '[:lower:]' '[:upper:]' | sort -u > /tmp/sweep-owned.txt

# 1. 활성 워크트리 enumerate
git worktree list --porcelain | awk '/^worktree / {print $2}' > /tmp/sweep-worktrees.txt

# 2. 각 워크트리에 대해 스코프 판정 후 머지 여부 판정
swept=()
sweep_failed=()
out_of_scope=()
while IFS= read -r wt; do
  # 메인 리포지토리(브랜치 develop)는 건드리지 않는다
  br=$(git -C "$wt" branch --show-current 2>/dev/null)
  [ -z "$br" ] || [ "$br" = "develop" ] && continue

  # 스코프 한정: 브랜치명 prefix 이슈 번호가 본 autopilot 소유 집합에 없으면 제외.
  # 다른 세션의 워크트리를 강제 제거하지 않기 위한 근본 가드.
  wt_ticket=$(printf '%s' "$br" | grep -oiE '^[A-Z]+-[0-9]+' | tr '[:lower:]' '[:upper:]')
  if [ -z "$wt_ticket" ] || ! grep -qxF "$wt_ticket" /tmp/sweep-owned.txt; then
    out_of_scope+=("$br")
    continue
  fi

  # 판정 우선순위:
  # (a) .process-state.json의 merged 필드 → 이미 머지 확정
  # (b) gh pr list로 브랜치명 매칭 → state=MERGED
  merged=false
  if [ -f "$wt/.process-state.json" ]; then
    if jq -e '.merged' "$wt/.process-state.json" > /dev/null 2>&1; then
      merged=true
    fi
  fi
  if [ "$merged" = "false" ]; then
    pr_state=$(gh pr list --repo E5presso/spakky-framework --head "$br" --state merged --json number --jq '.[0].number' 2>/dev/null)
    [ -n "$pr_state" ] && merged=true
  fi
  [ "$merged" = "false" ] && continue

  # 머지 확정 → 정리 시도 (process-ticket Phase 8 §5-A와 동일 절차)
  repo_root=$(git -C "$wt" rev-parse --path-format=absolute --git-common-dir | xargs dirname)
  if git -C "$repo_root" worktree remove "$wt" --force 2>&1 | tee /tmp/sweep-wt.log; then
    git -C "$repo_root" branch -D "$br" 2>&1 | tee /tmp/sweep-br.log || true
    swept+=("$br")
  else
    sweep_failed+=("$br: $(cat /tmp/sweep-wt.log)")
  fi
done < /tmp/sweep-worktrees.txt
```

판정 우선순위 근거:

1. 스코프 한정이 머지 판정에 선행한다 — 본 autopilot 소유 이슈 집합 밖의 워크트리는 머지 여부와 무관하게 `out_of_scope`로 분류하고 제거 대상에서 빼낸다. 다른 세션의 워크트리가 우연히 머지 상태여도 본 sweep이 건드리지 않는다.
2. `.process-state.json`의 `merged` 필드는 process-ticket Phase 8 §2가 머지 직후 동기 기록하므로 1차 sentinel.
3. state 파일이 누락·결손이면 GitHub PR 상태(`gh pr list ... --state merged`)로 fallback.
4. 둘 다 false이면 정리 후보 아님 — 진행 중이거나 awaiting-review일 수 있다.

본 sweep은 idempotent하다 — 재실행 시 이미 정리된 워크트리는 enumerate 결과에 없으므로 후보가 0개로 좁혀진다.

sweep 결과는 §6-1 리포트에 별도 섹션으로 노출하여 외부에서 본 단계 실행 여부를 검증할 수 있게 한다 (silent skip 금지).

본 sweep은 회피 경로가 아니다 — process-ticket Phase 8 §5 워크트리 정리가 1차 정리 수단이며, 본 단계는 누락된 경우의 외부 안전망. 두 경로가 모두 잠재 결함을 가진 적대적 관계로 운영되어야 잔존 회귀를 차단한다.

### Agent Team 정리

§3-2-bis에서 만든 autopilot team을 정리한다. 본 단계는 워크트리 sweep 완료 직후에 둔다 (sweep 안에서 SendMessage 사용 가능성 보존).

**종결 멤버는 TaskStop으로 정리한다 (cold-wake 금지).** wave 전 멤버가 종결 신호(정규형 `terminal-return` 수신 또는 `worktree-cleanup-req` 송신)로 확정 + idle인 시점에, 각 멤버를 spawn 시 반환된 task_id로 `TaskStop(task_id: <member>)` 호출하여 추론 0토큰으로 정지시킨 뒤 `TeamDelete(team_name: "{TEAM_NAME}")`를 1회 호출한다. `shutdown_request`는 멤버 컨텍스트를 cold-wake하여 approve 1줄 산출에 전체 컨텍스트(TTL 만료 시 통째)를 재과금하므로 종결 멤버 정리에 쓰지 않는다.

본 TaskStop은 `new-ticket-intake.md` "금지 행동" ②(진행 중 sub-agent의 외부 TaskStop 종료)와 직교한다 — 그쪽은 작업 도중(non-terminal) 멤버를 강제 종료하는 회피 경로를 막고, 본 단계는 이미 종결 신호로 확정된 idle 멤버만 대상으로 한다. 미종결 멤버가 wave 결과 사전에 남아 있으면 본 정리에 진입하지 않는다 (Phase 3 §3-3-bis stuck/terminal-return-probe가 선행 회수).

`TeamDelete`가 잔존 멤버로 실패하면 비차단 — 추가 cold-wake 왕복 없이 1줄 알림만 남긴다 (세션 종료 후 다음 autopilot 호출이 동일 team_name으로 진입할 때 stale config 충돌 가능성 외에는 영향 없음).

## 6-1. 최종 리포트 출력

전체 실행 결과를 단일 메시지로 출력한다.

```
## Autopilot 실행 완료 ({대상 수}개 이슈, {웨이브 수}개 웨이브)

### 이슈 SDLC 결과

| 웨이브 | 이슈 | 상태 | PR | 비고 |
|--------|------|------|-----|------|
| 0 | <ISSUE-NUMBER> | merged | #N | — |
| 0 | <ISSUE-NUMBER> | awaiting-review | #N | 사람 리뷰어 코멘트 N건 대기 |
| 1 | <ISSUE-NUMBER> | failed | — | Phase 4 검증 실패 |
| 2 | <ISSUE-NUMBER> | skipped | — | 선행 <ISSUE-NUMBER> 실패 |

### 마일스톤 의도 감사 (Phase 4)

- 충족: {N}개 가치 항목
- gap: {M}개 — 후속 이슈 후보 {목록}
- critical: {K}개 (있을 시 질의 메시지)

### 문서 동기화 (Phase 5)

- 갱신 문서: {경로 목록}
- sync-docs PR: {URL}

### 자기 운영 결함 메타-감지 (Phase 3.6)

- 매치 시그널 ({len(matched_signals)}개): {시그널명 목록 — 비어 있으면 `없음`}
- 자동 생성 이슈 ({len(meta_queue_acc)}개): {이슈 번호 목록 + URL}
- 메타 fix wave 머지 ({merged}/{total})

### 부모 epic 자동 마감 (Phase 6-0)

- 식별된 부모 epic ({len(parent_epics)}개): {parent_epics.keys() — 비어 있으면 `없음`}
- 자동 Done 처리 ({len(auto_done_acc)}개): {auto_done_acc 목록}
- 자동 Done 보류 ({len(auto_done_pending)}개): {auto_done_pending 목록 — 항상 노출 (silent skip 금지)}
  - 형식: `<EPIC-ID>: 자식 미완료 N개: [<ISSUE-NUMBERS>]`
  - 형식: `<EPIC-ID>: save_issue 호출 후 상태 재조회 = <state> (Done 아님 — silent failure 의심)`

### 잔존 워크트리 sweep (Phase 6-0-bis)

- 정리됨 ({len(swept)}개): {swept 목록 — 비어 있으면 `없음 (process-ticket Phase 8 §5가 모든 워크트리를 1차 정리)`}
- 정리 실패 ({len(sweep_failed)}개): {sweep_failed 목록 — 사유 1줄 포함, 항상 노출 (silent skip 금지)}
- 범위 외 제외 ({len(out_of_scope)}개): {out_of_scope 목록 — 본 autopilot 소유 이슈 집합 밖이라 sweep 대상에서 제외한 워크트리 브랜치. 스코프 한정이 동작했음을 외부에서 검증 가능하게 함}

### 사용자 조치 필요

- **사람 응답 대기 PR** ({n}개): {PR URL 목록}
- **실패 이슈** ({k}개): {이슈 URL 목록} — 원인 조사 후 개별 `/process-ticket`으로 재시도
- **후속 이슈 메타데이터 보류** ({b}개): {spawned_metadata_blocked 목록 — 누락 필드와 issue URL 포함}. 라벨/마일스톤/assignee 보정 실패로 spawn하지 않은 이슈이며, 생성 여부를 사용자에게 다시 묻는 항목이 아니다.
```
