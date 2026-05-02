# Phase 6: 최종 리포트

## 6-0. 부모 epic 자동 close 처리 (강제 게이트 — 리포트 출력 직전)

Phase 5 sync-docs 종료 후 최종 리포트 출력 전에, 자식 티켓이 모두 머지된 부모 epic을 GitHub `closed` 상태로 일괄 마감한다. 자식 머지 결과는 이미 §3-3에서 `merged_children`에 누적되어 있고, 부모 ↔ 자식 매핑은 Phase 1 §3에서 `parent_epics`에 저장되어 있으므로 추가 외부 조회는 필요 없다.

**강제 게이트**: 본 단계는 Phase 6 최종 리포트 출력의 **선행 필수 단계**다. `parent_epics`가 비어 있더라도 본 단계 진입 사실 자체를 리포트에 노출(아래 §6-1 "부모 epic 자동 마감" 섹션에 `대상 부모 epic 0개 — 본 실행에서 식별된 epic 없음`)하여 외부에서 §6-0 실행 여부를 검증할 수 있게 한다. silent skip은 회귀를 발생시키므로, Phase 6 리포트 출력 직전 본 단계의 실행 흔적이 리포트에 포함되지 않으면 abort.

알고리즘:

```
auto_done_acc = []
auto_done_pending = []
for epic_number, children in parent_epics.items():
  if all(child in merged_children for child in children):
    try:
      gh issue close <epic_number> --reason completed
      # 호출 직후 상태 재조회 검증
      verify = gh issue view <epic_number> --json state
      if verify.state == "closed":
        auto_done_acc.append(epic_number)
      else:
        auto_done_pending.append((epic_number, f"close 호출 후 상태 재조회 = {verify.state} (closed 아님 — silent failure 의심)"))
    except Exception as e:
      auto_done_pending.append((epic_number, f"GitHub API 실패: {e}"))
  else:
    pending_children = [c for c in children if c not in merged_children]
    auto_done_pending.append((epic_number, f"자식 미완료 {len(pending_children)}개: {pending_children}"))
```

핵심 속성:

1. 외부 자식(대상 마일스톤 외)은 `parent_epics` 단계에서 이미 제외되었으므로 본 검증에 영향을 주지 않는다.
2. GitHub API 호출 실패는 charter §4-A 질의 트리거로 분류하지 않고 `auto_done_pending`에 사유 1줄과 함께 기록 — 사용자가 최종 리포트에서 수동 마감을 결정한다.
3. 자식이 비어 있는 부모는 Phase 1 §3 판정 기준상 부모 epic으로 식별되지 않으므로 `parent_epics`에 들어오지 않는다.
4. 자기 마감 절대 금지 — 본 단계는 부모 epic만 대상으로 하며, 본 autopilot 인자 자체(예: 마일스톤 트래킹 이슈)에 직접 적용되지 않는다.

## 6-0-bis. 잔존 워크트리 sweep (외부 안전망)

process-ticket Phase 8 cleanup이 어떤 사유로든 누락되어 머지된 PR의 워크트리·로컬 브랜치가 남는 케이스에 대비해, 본 단계가 wave 종료 시점의 외부 안전망으로 동작한다. process-ticket Phase 8이 정상 실행된 워크트리는 이미 제거되어 본 sweep의 후보가 아니므로 idempotent하다.

알고리즘:

```bash
# 1. 활성 워크트리 enumerate
git worktree list --porcelain | awk '/^worktree / {print $2}' > /tmp/sweep-worktrees.txt

# 2. 각 워크트리에 대해 머지 여부 판정
swept=()
sweep_failed=()
while IFS= read -r wt; do
  # 메인 리포지토리(브랜치 develop / main)는 건드리지 않는다
  br=$(git -C "$wt" branch --show-current 2>/dev/null)
  [ -z "$br" ] || [ "$br" = "develop" ] || [ "$br" = "main" ] && continue

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

  # 머지 확정 → 정리 시도 (process-ticket Phase 8 §4와 동일 절차)
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

1. `.process-state.json`의 `merged` 필드는 process-ticket Phase 8 §2가 머지 직후 동기 기록하므로 1차 sentinel.
2. state 파일이 누락·결손이면 GitHub PR 상태(`gh pr list ... --state merged`)로 fallback.
3. 둘 다 false이면 정리 후보 아님 — 진행 중이거나 awaiting-review일 수 있다.

본 sweep은 idempotent하다 — 재실행 시 이미 정리된 워크트리는 enumerate 결과에 없으므로 후보가 0개로 좁혀진다.

sweep 결과는 §6-1 리포트에 별도 섹션으로 노출하여 외부에서 본 단계 실행 여부를 검증할 수 있게 한다 (silent skip 금지).

본 sweep은 회피 경로가 아니다 — process-ticket Phase 8 §4가 1차 정리 수단이며, 본 단계는 누락된 경우의 외부 안전망. 두 경로가 모두 잠재 결함을 가진 적대적 관계로 운영되어야 잔존 회귀를 차단한다.

### Agent Team 정리

§3-2-bis에서 만든 autopilot team을 정리한다 — `TeamDelete(team_name: "{TEAM_NAME}")`. 본 호출은 워크트리 sweep 완료 직후에 둔다 (sweep 안에서 SendMessage 사용 가능성 보존). team 정리 실패는 비차단 — 세션 종료 후 다음 autopilot 호출이 동일 team_name으로 진입할 때 stale config 충돌 가능성 외에는 영향 없으므로 1줄 알림만 남긴다.

## 6-1. 최종 리포트 출력

전체 실행 결과를 단일 메시지로 출력한다.

```
## Autopilot 실행 완료 ({대상 수}개 티켓, {웨이브 수}개 웨이브)

### 티켓 SDLC 결과

| 웨이브 | 티켓 | 상태 | PR | 비고 |
|--------|------|------|-----|------|
| 0 | #<TICKET-NUMBER> | merged | #N | — |
| 0 | #<TICKET-NUMBER> | awaiting-review | #N | 사람 리뷰어 코멘트 N건 대기 |
| 1 | #<TICKET-NUMBER> | failed | — | Phase 4 검증 실패 |
| 2 | #<TICKET-NUMBER> | skipped | — | 선행 #<TICKET-NUMBER> 실패 |

### 마일스톤 의도 감사 (Phase 4)

- 충족: {N}개 가치 항목
- gap: {M}개 — 후속 티켓 후보 {목록}
- critical: {K}개 (있을 시 질의 메시지)

### 문서 동기화 (Phase 5)

- 갱신 문서: {경로 목록}
- sync-docs PR: {URL}

### 자기 운영 결함 메타-감지 (Phase 3.6)

- 매치 시그널 ({len(matched_signals)}개): {시그널명 목록 — 비어 있으면 `없음`}
- 자동 생성 티켓 ({len(meta_queue_acc)}개): {티켓 번호 목록 + URL}
- 메타 fix wave 머지 ({merged}/{total})

### 부모 epic 자동 마감 (Phase 6-0)

- 식별된 부모 epic ({len(parent_epics)}개): {parent_epics.keys() — 비어 있으면 `없음`}
- 자동 close 처리 ({len(auto_done_acc)}개): {auto_done_acc 목록}
- 자동 close 보류 ({len(auto_done_pending)}개): {auto_done_pending 목록 — 항상 노출 (silent skip 금지)}
  - 형식: `#<EPIC-NUMBER>: 자식 미완료 N개: [<TICKET-NUMBERS>]`
  - 형식: `#<EPIC-NUMBER>: close 호출 후 상태 재조회 = <state> (closed 아님 — silent failure 의심)`

### 잔존 워크트리 sweep (Phase 6-0-bis)

- 정리됨 ({len(swept)}개): {swept 목록 — 비어 있으면 `없음 (process-ticket Phase 8 §4가 모든 워크트리를 1차 정리)`}
- 정리 실패 ({len(sweep_failed)}개): {sweep_failed 목록 — 사유 1줄 포함, 항상 노출 (silent skip 금지)}

### 사용자 조치 필요

- **사람 응답 대기 PR** ({n}개): {PR URL 목록}
- **실패 티켓** ({k}개): {티켓 URL 목록} — 원인 조사 후 개별 `process-ticket`으로 재시도
- **gap 후속 티켓 생성 질의** (해당 시): `AskUserQuestion`으로 생성 여부 확인
```
