---
name: monitor-pr
description: PR의 CI/리뷰 상태를 30초 주기 polling으로 감시하여 이벤트 발생 시 분기 처리합니다.
argument-hint: "<pr-number>"
user-invocable: false
---

# Monitor PR

PR 번호를 받아 고정 30초 polling으로 상태를 감시하고 분기 처리한다.

## 절대 명령 (서브에이전트 본인 책무 — 의역·완화 금지)

> **너는(이 스킬을 실행하는 서브에이전트) 자기 turn 안에서 직접 `watch.sh`를 포그라운드 Bash로 호출한다. `watch.sh`가 EVENT 또는 DONE을 stdout으로 1회 emit하고 종료할 때까지 너의 turn은 그 단일 Bash 호출이 점유하며, 그 사이에 너는 turn을 종료하지 않는다. EVENT가 나오면 §"이벤트 분기" 표대로 핸들러를 실행한 뒤 즉시 INIT으로 복귀하여 `watch.sh`를 다시 호출한다. DONE(`reason in {merged, mergeable-clean, closed-without-merge, awaiting-human-review}`)이 나올 때까지 이 INIT → LISTENING → 분기 → INIT 루프를 절대 빠져나가지 않는다.**

이 명령은 모델이 "polling을 외부에 위임하면 토큰을 아낄 수 있다", "결과가 오래 걸릴 것 같으니 자리를 비우자", "watch가 동작 중이라고 보고하면 충분하다" 같은 합리화로 회피할 수 있는 단일 결정 지점이다. 따라서 다음 4가지 회피 경로는 **명시적으로 안티패턴**이며, 본 스킬을 호출하는 어떤 컨텍스트에서도 채택되지 않는다:

1. **백그라운드 후 turn 종료** — `watch.sh`/`Monitor`/외부 스크립트를 `&` / `nohup` / `run_in_background: true` / `ScheduleWakeup` / `CronCreate`로 띄운 뒤 "monitor armed" 같은 보고와 함께 자기 turn을 종료하는 패턴.
2. **외부 알림 위임** — "다음 cycle 결과는 별도 알림으로 전달될 것"·"사용자가 변화를 알려줄 것"·"webhook이 들어오면 처리할 것" 같은 가정으로 polling 책임을 outsourcing하는 패턴. 본 스킬에 외부 알림 경로는 존재하지 않는다.
3. **1~2회 polling 후 종료** — `poll.sh` 또는 `watch.sh`를 1~2 cycle 돌고 "CI 진행 중", "변화 없음", "5–10분 더 걸릴 가능성"으로 판단하여 turn을 종료하는 패턴. 종료 조건은 시간이나 cycle 수가 아니라 `DONE` reason이다.
4. **EVENT consumer 부재** — `watch.sh`만 호출하고 stdout 출력의 `reason` 값을 case 분기하지 않은 채 turn을 종료하는 패턴. EVENT 핸들러 정의가 SKILL.md에 있어도 case 분기 주체가 살아 있지 않으면 dead code가 된다.

위 4종 안티패턴은 §"서브에이전트 조기 종료 회귀 시그널"에서 구체 종료 메시지로 다시 한 번 명시되며, `/evaluate-harness`는 본 시그널이 회귀로 관찰될 때 Critical로 차단한다.

### DONE 즉시 정지 (terminal stop — 추가 호출 금지)

`watch.sh`가 `DONE reason in {merged, mergeable-clean, closed-without-merge, awaiting-human-review}`을 emit하는 순간 본 스킬은 종료다. 호출자는 그 시점에 **추가 `watch.sh` / `poll.sh` / `gh pr view` 호출을 만들지 않는다.** terminal reason 처리는 reason별로 1:1 고정이며 추가 cycle을 요구하지 않는다:

- `reason=merged` → Phase 8 cleanup 1회 실행 후 turn 종료.
- `reason=mergeable-clean` → Phase 7 머지 게이트로 전환 후 turn 종료.
- `reason=closed-without-merge` → 결과 보고 (`status: failed`, `failed_reason: PR closed without merge`) 후 turn 종료.
- `reason=awaiting-human-review` → 결과 보고 (`status: awaiting-review`, `pending_human_comments: <bot CH2 코멘트 URL>`) 후 turn 종료. 봇이 HEAD 를 평가했고 의도적으로 review submission 대신 CH2 코멘트로 휴먼 리뷰 의견을 남긴 상태이므로, 추가 polling 은 봇 재평가 트리거 부재로 무의미하다 — 휴먼 리뷰어가 응답할 때까지 본 PR 의 자동 진행은 정지한다.

"안전을 위해 한 번 더 polling" / "mergeStateStatus 재검증" / "다음 cycle에 변화가 있는지" 류 추가 호출은 머지 후 dead time을 누적시키며 본 절이 명시적으로 차단한다 — 추가 cycle은 §"이벤트 분기"의 EVENT consumer 루프 안에서만 의미가 있다.

## 원칙

- **30초 고정 polling 단일 경로.** webhook, exponent backoff, 가변 간격 금지.
- **포그라운드 `watch.sh` 단일 호출이 정상 경로다.** 호출자(메인 또는 서브에이전트)는 `watch.sh`를 자기 turn 안에서 Bash 도구로 1회 호출한다. `watch.sh`는 단일 Bash 호출 안에서 무한 루프(30초 sleep + 스냅샷)를 돌며 EVENT 또는 DONE이 관찰될 때까지 블록하므로, 호출자의 turn은 스크립트가 종료할 때까지 차단된다 — "백그라운드 알림 수신"으로 자기 turn을 종료할 여지가 구조적으로 사라진다.
- **`poll.sh`는 1회성 스냅샷 전용**이며, INIT 게이트 직후 baseline 확보·디버깅 검증에만 사용한다. `poll.sh`를 LISTENING 루프에서 매 cycle 재호출하지 않는다 — `watch.sh`로 단일화한다.
- **외부 백그라운드 polling 경로 전부 금지.** 호출 컨텍스트(메인/서브에이전트) 무관하게 동일하게 적용된다 — 이름만 다를 뿐 "에이전트 제어 밖에서 돌아가는 polling"이라는 본질이 같아 이벤트 누락·경로 우회·turn 종료를 일으킨다:
  - `Monitor` 도구 (until-loop 포함 어떤 형태로도 금지)
  - `run_in_background: true` (Bash 도구) — `watch.sh`도 반드시 포그라운드 (`run_in_background: false` 또는 미지정)로 호출한다.
  - `ScheduleWakeup` / `CronCreate`
  - 별도 무한 루프 백그라운드 스크립트
  - 추가 `sleep`, 가변/증가 간격, exponent backoff
- **서브에이전트 컨텍스트에서는 백그라운드 알림이 도달하지 않는다.** `Monitor`/`run_in_background`로 polling을 외부화하면 서브에이전트는 알림 수신처가 없어 turn 종료 → 머지 전 조기 exit. 본 스킬이 `watch.sh` 단일 포그라운드 호출을 강제하는 이유다 (회귀 시그널은 §"서브에이전트 조기 종료 회귀 시그널" 참조).
- **스크립트는 raw 상태만 출력한다.** 이벤트 분류/비교는 호출자(에이전트)가 직전 결과와 비교하여 판단한다.
- **임의 shell 명령 호출 절대 금지.** 호출자는 본 스킬이 명시한 스크립트(`poll.sh`, `collect_comments.sh`)와 명시된 다른 스킬(`/triage-comments`, `/plan-issues`, `/check`, `/commit`)만 호출한다. 아래는 모두 금지:
  - `gh pr view`, `gh pr checks`, `gh pr diff`, `gh api repos/...` 직접 호출
  - `git diff`, `git log`, `git status` 등으로 PR/CI 상태를 자체 추론
  - 코멘트 본문을 잘 모르겠다는 이유로 별도 `gh api` 호출
  - "더 자세한 상태를 확인하기 위해" 새 명령 도입
  - 스크립트 출력이 부족해 보여도 추가 명령으로 보강 시도

  스크립트 출력만으로 분기 판단이 불가능하다면 그것은 스크립트의 결함이다 — 사용자에게 보고하고 스크립트를 수정한다 (`/optimize-harness`). 호출자가 우회 명령으로 메우지 않는다.
- **PR/이슈 mutation도 정의된 sub-skill만.** PR 메타 변경(`gh pr edit`), 코멘트 reply, 라벨 추가 등은 모두 `/triage-comments` 등 정의된 sub-skill을 통한다. 호출자가 직접 `gh pr edit` / `gh api ... replies` 호출 금지. (코멘트 reply 마커 규칙은 sub-skill이 책임진다.)

## 상태 머신

```
INIT (미처리 코멘트 확인 — MUST)
  ├─ [코멘트 있음] → TRIAGE → INIT
  └─ [코멘트 없음] → LISTENING

LISTENING (watch.sh 단일 포그라운드 호출 — EVENT 또는 DONE까지 블록)
  ├─ EVENT reason=comments-changed         → COLLECT → TRIAGE → INIT
  ├─ EVENT reason=review-decision-changed  → COLLECT → TRIAGE 게이트 → INIT
  ├─ EVENT reason=ci-failed                → CI_FIX → INIT
  ├─ EVENT reason=merge-dirty              → RESOLVE → INIT
  ├─ EVENT reason=bot-stuck                → RETRIGGER (빈 커밋 push, 3회 상한) → INIT
  ├─ EVENT reason=heartbeat                → SendMessage tick ping → LISTENING (watch.sh 재호출)
  ├─ DONE  reason=awaiting-human-review    → 종료 (status=awaiting-review 보고)
  └─ DONE  reason=mergeable-clean | merged  → 종료 (Phase 7)
```

## INIT: 미처리 코멘트 확인

**MUST**: polling 시작 전과 매 재시작 전에 반드시 실행.

```bash
REPO=E5presso/spakky-framework PR_NUMBER={N} bash {SKILL_DIR}/scripts/collect_comments.sh
```

### 트리아지 게이트 (MUST)

`TOTAL > 0` → `/triage-comments {PR}` 무조건 실행. 예외 없음.
`TOTAL == 0` → polling 시작.

**금지**: 에이전트가 코멘트 내용을 보고 "처리 불필요"로 판단하고 triage를 건너뛰는 것. "무지성 반영"(코멘트를 보고 곧바로 코드를 수정하는 것)도 동일하게 금지 — 판단은 `/triage-comments`에서만 이루어진다.

### 에이전트 reply 마커 (MUST)

`collect_comments.sh`는 에이전트의 reply를 본문의 invisible marker `<!-- claude-agent-reply to=<id> -->`로 식별한다. `<id>`는 응답이 겨냥하는 **대상 코멘트/리뷰의 숫자 GitHub ID** (인라인 코멘트 id, 이슈 코멘트 id, 리뷰 id 중 하나).

이 ID 태그 방식으로 "처리된 대상 집합"을 명시적으로 구성하므로, thread·timestamp 휴리스틱이 놓치던 교차-thread 코멘트(예: claude[bot] 리뷰가 다른 thread와 섞여 들어오는 경우)까지 정확히 필터링한다.

PR 코멘트/리뷰 reply를 작성하는 모든 `gh api` 호출은 본문에 `to=<id>` 마커를 포함해야 한다. `<id>`가 누락된 평문 마커는 수신자로부터 단 1건의 자기 응답으로만 인식되며 대상 매칭이 되지 않아 원본 코멘트가 계속 미처리 상태로 남는다.

```bash
# 인라인 코멘트 reply
gh api -X POST repos/$REPO/pulls/$PR/comments/$ID/replies -f body="...본문...

<!-- claude-agent-reply to=$ID -->"

# 일반 PR 코멘트 응답 (CH2는 reply 전용 엔드포인트가 없어 별도 issue 코멘트로 post)
gh api -X POST repos/$REPO/issues/$PR/comments -f body="...본문...

<!-- claude-agent-reply to=$ISSUE_COMMENT_ID -->"

# 리뷰 본문 응답 (필요 시 issue 코멘트 경유)
gh api -X POST repos/$REPO/issues/$PR/comments -f body="...본문...

<!-- claude-agent-reply to=$REVIEW_ID -->"
```

## LISTENING: 포그라운드 watch.sh 단일 호출

호출자는 자기 turn 안에서 `watch.sh`를 Bash 도구로 1회 호출한다. 스크립트는 단일 Bash 호출 안에서 30초 sleep + 스냅샷 cycle을 무한 반복하며, EVENT 또는 DONE이 관찰될 때까지 블록한다 — 호출자의 turn은 스크립트가 종료할 때까지 자동으로 점유된다.

```bash
REPO=E5presso/spakky-framework PR_NUMBER={N} \
  PREV_STATE_FILE={워크트리 경로}/.monitor-pr-state.json \
  PREV_REVIEW_DECISION={직전 결과 또는 빈 값} \
  bash {SKILL_DIR}/scripts/watch.sh
```

`PREV_STATE_FILE`은 직전 cycle에 관찰된 모든 코멘트/리뷰의 `(id, updatedAt)` 페어를 채널별로 저장하는 JSON 파일 경로다. 매 cycle 종료 시 현재 스냅샷으로 덮어써지며, 호출자는 동일 경로를 다음 호출에 그대로 전달한다. 파일이 없거나 비어 있으면 첫 cycle을 baseline으로 채우고 EVENT를 보고하지 않는다.

> **반드시 포그라운드.** `run_in_background: true`로 호출하면 본 스킬의 핵심 차단력(단일 turn 점유)이 무너진다 — `Monitor` 도구·`ScheduleWakeup`과 본질이 같아진다. Bash tool의 기본 동작은 포그라운드이므로 별도 플래그 지정 없이 호출한다.

스크립트 출력 형식:

```
EVENT                              # 또는 DONE
mergeState=<X>
reviewDecision=<Y>
commentCount=<N>
reviewCommentCount=<N>
pendingChecks=<N>
failedChecks=<N>
reason=<comments-changed|review-decision-changed|ci-failed|merge-dirty|mergeable-clean|merged|awaiting-human-review>
staleHandledIds=<id1,id2,...>      # reason=comments-changed 일 때만, in-place 갱신된 id 목록 (없으면 빈 값)
```

### `(id, updatedAt)` 캐시 기반 변화 감지 (MUST)

`watch.sh`는 매 cycle마다 CH1(인라인)/CH2(일반)/CH3(리뷰) 3채널의 모든 row를 수집하여 `(id → updatedAt)` 맵을 만들고 `PREV_STATE_FILE`의 직전 맵과 비교한다. EVENT(`reason=comments-changed`)는 다음 두 경우 모두 발생한다:

1. **신규 row** — 직전 캐시에 없던 id 등장 (기존 동작).
2. **in-place 갱신** — 직전 캐시에 존재하지만 `updatedAt`이 더 큰 id 등장. claude bot이 새 푸시 시 기존 review/코멘트를 재작성(`createdAt`은 그대로, `updatedAt`만 증가)하는 케이스에서 발생.

in-place 갱신이 감지된 id는 `staleHandledIds=` 라인으로 함께 출력된다. 호출자는 이 값을 `collect_comments.sh`의 `STALE_HANDLED_IDS` 환경변수로 전달하여, 해당 id의 기존 `<!-- claude-agent-reply to=<id> -->` 마커를 무효화하고 변경된 본문을 재수집·재triage 대상으로 되돌린다.

> **CH3(리뷰 본문) 한계**: GitHub Reviews API는 `updated_at`을 노출하지 않아 `submitted_at`을 baseline으로 쓴다. 리뷰 본문 자체의 in-place 갱신은 본 스킬 범위 밖이며, 실제 회귀(claude bot in-place 갱신)는 CH1/CH2에서 관찰된다.

매 cycle마다 stderr에 1줄 진행 로그가 출력되어 살아있음을 가시화한다 (`[watch.sh] <ts> mergeState=... ...`).

호출자는 출력의 첫 줄(EVENT 또는 DONE)과 `reason` 값을 §"이벤트 분기" 표로 처리한다. EVENT 처리 후에는 다음 cycle baseline을 갱신하여 `watch.sh`를 다시 1회 호출한다.

**긴 대기가 필요해도 동일 규칙**: 단일 `watch.sh` 호출이 cycle을 내부에서 반복한다. "긴 대기가 예상되니 백그라운드로 돌리고 알림을 기다리자"로 자기 turn을 종료하지 않는다 (서브에이전트 조기 종료의 직접 원인).

### EVENT consumer 루프 (MUST — 호출자 책무 명시)

`watch.sh`는 EVENT/DONE 블록을 stdout으로 1회 emit하고 종료한다. 호출자(에이전트)는 **출력 블록을 읽고 `reason` 값으로 case 분기하여 핸들러를 실행**해야 한다 — 핸들러 정의가 SKILL.md에 있어도 case 분기 주체가 없으면 dead code가 된다.

호출자는 자기 turn 안에서 다음 형태로 `watch.sh` 호출 + EVENT 분기를 실행한다 — 단일 Bash 호출 안에서 watch.sh 출력을 직접 case로 분기하는 패턴이다:

```bash
OUT=$(REPO=E5presso/spakky-framework PR_NUMBER={N} \
  PREV_STATE_FILE={워크트리}/.monitor-pr-state.json \
  bash {SKILL_DIR}/scripts/watch.sh)

MARKER=$(echo "$OUT" | head -n 1)              # EVENT | DONE
REASON=$(echo "$OUT" | grep '^reason=' | cut -d= -f2)
STALE=$(echo "$OUT" | grep '^staleHandledIds=' | cut -d= -f2)

case "$MARKER:$REASON" in
  "EVENT:comments-changed")        # STALE_HANDLED_IDS=$STALE collect_comments.sh → /triage-comments → INIT
    ;;
  "EVENT:review-decision-changed") # collect_comments.sh → /triage-comments → INIT
    ;;
  "EVENT:ci-failed")               # 로컬 CI 재현 → 수정 → push → INIT
    ;;
  "EVENT:merge-dirty")             # rebase/conflict 해결 → push → INIT
    ;;
  "EVENT:bot-stuck")               # 빈 커밋 retrigger (3회 상한) → INIT
    ;;
  "EVENT:heartbeat")                # SendMessage tick ping 1줄 → INIT (watch.sh 재호출, cycle 카운터 0부터 재시작)
    ;;
  "DONE:mergeable-clean"|"DONE:merged")
    # Phase 7/8 전환
    ;;
  "DONE:closed-without-merge")
    # status: failed
    ;;
  "DONE:awaiting-human-review")
    # status: awaiting-review (봇이 HEAD 평가 후 휴먼 리뷰 위임 — pending_human_comments 보고 후 종료)
    ;;
esac
```

핸들러 본문(주석 자리)은 §"이벤트 분기" 표의 처리 컬럼에 1:1로 매핑된다. 분기 후 종료 조건(DONE)이 아니면 INIT으로 복귀하여 `watch.sh`를 다시 1회 호출한다.

> **consumer 부재 시 동작 미정의 (MUST)**: 호출자가 `watch.sh`만 호출하고 EVENT 블록을 case로 분기하지 않은 채 자기 turn을 종료하면 본 스킬은 동작하지 않는다. EVENT 핸들러 정의는 case 분기 주체가 살아 있는 동안에만 의미를 갖는다. "Watch armed. 알림 대기." 같은 turn 종료 메시지는 §"서브에이전트 조기 종료 회귀 시그널"의 직접 위반이다.

> **직렬화로 회피하지 않음 (회귀 방지)**: 병렬 PR이 다수 존재해도 본 fix는 동시 진행을 막는 직렬화가 아니다 — **각 PR을 처리하는 서브에이전트가 자기 turn 안에서 자기 PR의 EVENT consumer 루프를 살려 두면**, `merge-dirty`·`ci-failed` 등 모든 이벤트가 PR별로 독립 처리된다. 동시성 제약을 거는 우회 fix(autopilot wave 직렬화·동시 PR 1개 제한 등)를 본 스킬에 추가하지 않는다.

## 이벤트 분기

| `watch.sh` 출력 | 처리 |
|-----------|------|
| `EVENT reason=comments-changed` | `STALE_HANDLED_IDS={staleHandledIds 값} collect_comments.sh` 실행 → TRIAGE 게이트 → INIT (다음 `watch.sh` 호출) |
| `EVENT reason=review-decision-changed` | `collect_comments.sh` 실행 → TRIAGE 게이트 → INIT |
| `EVENT reason=ci-failed` | 로컬 CI 재현 → 수정 → push → INIT |
| `EVENT reason=merge-dirty` | 자동 rebase (§"Merge dirty — develop 자동 rebase") → INIT |
| `EVENT reason=bot-stuck` | 빈 커밋 retrigger (§"봇 응답 정체 retrigger") → INIT |
| `EVENT reason=heartbeat` | SendMessage tick ping (§"Heartbeat ping") → INIT (watch.sh 재호출) |
| `DONE reason=mergeable-clean` | 종료 (Phase 7 전환) |
| `DONE reason=merged` | 종료 (이미 머지됨 — Phase 8 정리만 수행) |
| `DONE reason=closed-without-merge` | 종료 (PR이 머지 없이 닫힘 — autopilot은 `status: failed`, `failed_reason: PR closed without merge`로 보고하고 다음 wave 진행 차단) |
| `DONE reason=awaiting-human-review` | 종료 (봇이 HEAD 평가 후 review submission 대신 CH2 코멘트로 휴먼 리뷰 위임 — `status: awaiting-review`, `pending_human_comments: <bot CH2 코멘트 URL>`로 보고하고 휴먼 응답 대기) |

### 코멘트 수집 (이벤트 핸들러)

```bash
REPO=E5presso/spakky-framework PR_NUMBER={N} \
  STALE_HANDLED_IDS={watch.sh의 staleHandledIds 값 또는 빈 값} \
  bash {SKILL_DIR}/scripts/collect_comments.sh
```

수집된 TOTAL > 0이면 반드시 `/triage-comments {PR}`을 호출한다. `STALE_HANDLED_IDS`에 포함된 id는 기존 reply 마커가 있어도 미처리로 재분류되어 본문이 재수집된다 — claude bot이 in-place로 갱신한 review/코멘트의 변경 본문이 triage에 다시 노출된다.

### 회귀 시나리오 (in-place 갱신)

claude bot이 동일 review id `R1`의 본문을 새 푸시 시 in-place로 재작성한 경우:

1. cycle N: `R1`의 `updatedAt = T0`, 캐시에 `{ch3: {R1: T0}}` 저장. 에이전트가 응답 후 `<!-- claude-agent-reply to=R1 -->` 마커 부착.
2. cycle N+1: claude bot이 새 푸시에 대응하여 `R1`을 in-place 갱신 (`updatedAt = T1 > T0`, body 변경).
3. `watch.sh`는 `R1`이 직전 캐시에 존재하지만 `updatedAt`이 증가했음을 감지 → `EVENT reason=comments-changed staleHandledIds=R1` 출력.
4. 에이전트는 `STALE_HANDLED_IDS=R1`로 `collect_comments.sh` 호출 → `R1`이 HANDLED_IDS에서 제거되어 변경된 본문이 다시 미처리 코멘트로 등장.
5. `/triage-comments`이 변경된 본문에 대해 재triage 수행.

### CI 실패

1. 로컬에서 변경 패키지 `/check` 실행으로 CI 재현 (모노레포 규칙 — 루트에서 직접 ruff/pyrefly/pytest 금지).
2. **로컬 통과 → 빈 커밋 push로 CI 자동 재트리거** (대부분 인프라 일시 실패):
   ```bash
   git commit --allow-empty -m "chore: Retrigger CI"
   git push
   ```
   push 후 `git rev-parse HEAD` 와 `git rev-parse @{u}` 비교로 remote 반영 검증. 재트리거 후에도 같은 체크가 또 실패하면 사용자에게 보고.
3. 로컬 실패 → 수정 → 커밋 & push.

> **PR close/reopen 금지** (AGENTS.md 절대 금지 사항). 빈 커밋 push만 허용.

### 봇 응답 정체 retrigger (`reason=bot-stuck`)

`watch.sh`가 다음 5-조건을 모두 만족하면 `EVENT reason=bot-stuck`을 송신한다:

(a) 모든 CI check가 COMPLETED (PENDING/IN_PROGRESS 0건)
(b) `mergeStateStatus != CLEAN`
(c) `reviewDecision != APPROVED`
(d) latest claude[bot] review의 `commit_id != HEAD oid` (또는 claude[bot] review 부재)
(e) claude[bot]이 HEAD commit 시점 이후로 CH2 issue comment 도 남기지 않았다

이 상태는 rebase 후 동일 트리·force-push 후 사실상 hash 미변경 등으로 봇이 신규 커밋으로 인식하지 않아 재리뷰 트리거가 누락된 정체다. CI는 끝났지만 GitHub가 아직 mergeable로 계산하지 않아 polling만 무한 반복된다.

**(e)의 의의 (회귀 차단)**: claude bot은 자동 승인 비적격 판정 시 formal review 대신 CH2 issue comment 로 "팀원 리뷰 필요" 의견을 남기는 경로를 가진다. 이 경우 봇은 현재 HEAD 를 평가했지만 의도적으로 review submission 을 하지 않은 것이며, 휴먼 리뷰어 승인을 대기해야 한다. (d) 만으로 판정하면 본 case 가 stuck 으로 잘못 분류되어 빈 커밋 retrigger 가 동일 판정만 재발행하면서 폴링·크레딧을 소진한다 — (e) 가 이 회귀를 차단한다.

**핸들러**: 빈 커밋 + push로 새 commit hash 생성 → 봇 재리뷰 + CI 재실행 유도.

```bash
git commit --allow-empty -m "chore: Retrigger bot review"
git push
git rev-parse HEAD
git rev-parse @{u}   # 위와 일치 확인
```

**상한 3회 (안전장치)**: 동일 PR에서 retrigger가 4회 차에 진입해야 하면 봇 장애·권한·repo 설정 등 휴리스틱 영역 밖 문제일 가능성이 높다. 사용자 질의로 분기하고 polling을 정지한다.

카운트는 워크트리 `.process-state.json`의 `bot_stuck_retrigger_count` 필드에 누적한다. 갱신·검사 절차:

```bash
STATE=.process-state.json
COUNT=$(jq -r '.bot_stuck_retrigger_count // 0' "$STATE" 2>/dev/null || echo 0)
if [ "$COUNT" -ge 3 ]; then
  # 사용자 질의 분기 — polling 정지, AskUserQuestion 호출
  echo "bot-stuck 3회 초과 — 사용자 질의"
  exit 0
fi
NEW=$((COUNT + 1))
tmp=$(mktemp)
jq --argjson n "$NEW" '.bot_stuck_retrigger_count = $n | .updated_at = (now | todateiso8601)' \
  "$STATE" > "$tmp" && mv "$tmp" "$STATE"
git commit --allow-empty -m "chore: Retrigger bot review (#$NEW)"
git push
```

상한 도달 시 `AskUserQuestion`으로 (1) 추가 retrigger 시도, (2) polling 중단·수동 개입, (3) PR close 등 중 사용자 판정을 받는다. 자체 판단으로 4회 차 retrigger를 강행하지 않는다.

### Merge dirty — develop 자동 rebase (`reason=merge-dirty`)

`mergeStateStatus=DIRTY`는 PR 브랜치와 `origin/develop`이 충돌하는 상태다. monitor 진입 후 develop에 다른 PR이 머지되어 DIRTY로 전환된 경우 호출자가 자동 rebase 없이 turn을 종료하면 stuck — polling 루프 안에서 develop이 다시 움직이는 케이스는 PR 생성 직전 1회 적용되는 conflict 핸들러로 커버되지 않으므로, monitor 루프가 자체 진입점으로 동일 절차를 재실행한다.

호출자는 워크트리 절대경로에서 다음을 순서대로 실행한다:

1. **fetch + rebase 시도**:
   ```bash
   git fetch origin develop
   git rebase origin/develop
   ```
2. **충돌 발생 시 의도 보존 휴리스틱**:
   - `git status --porcelain=v1`로 `UU` (both-modified) 파일 목록 확인.
   - 각 충돌 파일의 충돌 hunk(`<<<<<<<` / `=======` / `>>>>>>>` 사이)를 비교:
     - **단방향 변경** (한쪽 hunk가 비어 있거나, 한쪽이 다른 쪽의 superset이어서 한쪽 변경만 의미를 갖는 경우)은 변경된 쪽을 자동 채택 후 `git add <file>`.
     - **양방향 같은 줄 변경** (양쪽이 동일 줄을 서로 다르게 수정)은 true conflict — 즉시 `git rebase --abort` 후 사용자에게 질의하고 polling 일시 중단. 자율 채택 금지.
   - 모든 충돌이 자동 채택으로 해소되면 `git rebase --continue`로 진행. 단 한 건이라도 양방향이면 abort.
3. **force-with-lease push**:
   ```bash
   git push --force-with-lease
   git rev-parse HEAD
   git rev-parse @{u}   # 일치 확인
   ```
4. **polling 재개**: baseline을 갱신하여 `watch.sh`를 재호출 (CI 재트리거 대기).

#### 시도 횟수 가드 (상한 3회)

동일 PR에서 본 절차가 4회 차에 진입해야 하면 develop이 비정상적으로 빠르게 움직이거나 brittle한 충돌이 누적되는 상황이다. 사용자에게 질의하여 우선순위·전략을 재확인 후 polling을 정지한다.

카운트는 워크트리 `.process-state.json`의 `merge_dirty_rebase_count` 필드에 누적한다 (bot-stuck 카운트와 별개 키). 갱신·검사 절차:

```bash
STATE=.process-state.json
COUNT=$(jq -r '.merge_dirty_rebase_count // 0' "$STATE" 2>/dev/null || echo 0)
if [ "$COUNT" -ge 3 ]; then
  echo "merge-dirty rebase 3회 초과 — 사용자 질의"
  exit 0
fi
NEW=$((COUNT + 1))
tmp=$(mktemp)
jq --argjson n "$NEW" '.merge_dirty_rebase_count = $n | .updated_at = (now | todateiso8601)' \
  "$STATE" > "$tmp" && mv "$tmp" "$STATE"
git fetch origin develop
git rebase origin/develop
# (충돌 처리 — 위 휴리스틱)
git push --force-with-lease
```

#### 금지

- `git push --force` (lease 없이) 사용 금지 — 다른 협업자가 동시 push 한 경우 덮어쓴다.
- `git rebase --skip` 사용 금지 — 충돌 hunk를 통째로 버려 의도 손실.
- `EVENT reason=merge-dirty` 수신 직후 turn 종료 금지 — 본 절차를 즉시 실행하여 polling을 재개한다. "stuck인 것 같으니 사용자 보고 후 종료"도 동일하게 금지 — 질의는 시도 횟수 상한 도달 시에만.

### Heartbeat ping (`reason=heartbeat`)

`watch.sh`가 변화 없는 cycle을 6회(=3분) 누적하면 `EVENT reason=heartbeat`을 emit하고 종료한다. 호출자(서브에이전트)는 다음 1줄을 송신한 뒤 즉시 같은 turn 안에서 `watch.sh`를 재호출하여 polling을 재개한다 — 메인 세션이 monitor 루프를 hang으로 오판하지 않도록 가시화하는 장치다 (process-ticket SKILL.md "*Phase 내부 heartbeat*" 3분 주기 SSOT를 LISTENING 루프에서도 보장).

```
SendMessage(
  to: "team-lead",
  summary: "phase-tick {T}",
  message: "phase: monitor-pr | tick: poll <N> | pr=<#> | ci=<status> | review=<state>"
)
```

- `<N>`: 본 PR에 대해 누적된 heartbeat 송신 횟수 (1부터 시작, 매 송신마다 +1).
- `<#>`: PR 번호 (예: `12345`).
- `<status>`: `watch.sh` 출력의 `mergeState` 값 (예: `CLEAN`/`UNSTABLE`/`UNKNOWN`).
- `<state>`: `watch.sh` 출력의 `reviewDecision` 값 (예: `APPROVED`/`CHANGES_REQUESTED`/빈 값).

본 ping은 단방향이며 회신을 기다리지 않는다 — 송신 직후 `watch.sh`를 재호출하여 LISTENING으로 복귀한다 (cycle 카운터는 새 호출에서 0부터 재시작).

> **DONE 아님 (회귀 차단)**: `reason=heartbeat`은 EVENT이지 DONE이 아니다. 호출자가 본 reason을 받고 turn을 종료하면 §"서브에이전트 조기 종료 회귀 시그널" 안티패턴 (1)·(3)에 해당한다. 송신 후 즉시 재호출이 유일한 경로다.

### 트리아지 후 처리

1. `/triage-comments {PR}` 실행 (자동 승인).
   - 수용 → 코드 수정 + 커밋 & push + 스레드 응답
   - 반론 → 스레드에 근거
   - 보류 → `AskUserQuestion`
2. 리뷰어에게 재리뷰 요청: `gh pr edit {PR} --repo E5presso/spakky-framework --add-reviewer {LOGIN}`

## Polling 운영 규칙 (MUST)

- **자발적 중단 절대 금지.** 호출자는 아래 어떤 이유로도 polling 루프를 중단하지 않는다:
  - "토큰 비용이 든다"
  - "결과가 시간이 걸릴 것 같다" / "5–10분 뒤에 나올 가능성"
  - "사용자가 동석하고 있어 직접 처리 가능하다"
  - "변화 없는 상태가 N회 반복됐다"
  - "사용자에게 진행 결정을 묻는 것이 적절해 보인다"
  - "스킬이 백그라운드 알림을 책임진다고 판단되니 turn을 종료하자"
- 사용자가 명시적으로 "polling 중단"을 지시한 경우, 또는 PR이 종료 조건에 도달한 경우(Phase 7/8 진입)에만 종료한다.
- **`mergeState=UNKNOWN`인 경우는 GitHub 일시 계산 중 상태**다 — 다음 cycle을 기다린다. 그 외의 비정상(예: 모든 필드 빈 값)은 `poll.sh`가 실패한 신호이므로 사용자에게 보고한다.

## 서브에이전트 조기 종료 회귀 시그널 (MUST 차단)

다음 종료 메시지 패턴이 호출자 출력에 등장하는 즉시, 호출자는 **§"절대 명령" + 자발적 중단 금지 규칙을 동시 위반한 상태**다. 출력 직후 turn 종료가 따라오면 PR이 머지 전에 조기 exit한다. `/evaluate-harness`는 본 시그널을 회귀로 탐지하면 Critical로 차단한다.

§"절대 명령"의 4가지 안티패턴과 메시지 패턴은 다음과 같이 1:1 매핑된다:

| 안티패턴 | 종료 메시지 예시 |
|----------|------------------|
| 1. 백그라운드 후 turn 종료 | `Watch armed. 알림 대기.` / `Monitor running. I'll wait for terminal events.` / `Monitor running, waiting for events.` |
| 2. 외부 알림 위임 | `Per the skill rules, I should not poll manually.` / `다음 cycle 결과가 알림으로 도달하면 처리하겠습니다.` / `사용자가 PR 상태 변화를 알려주면 진행하겠습니다.` |
| 3. 1~2회 polling 후 종료 | `Continuing to wait for the remaining checks.` / `CI가 5–10분 더 걸릴 것 같아 일단 종료합니다.` / `변화 없는 cycle이 N회 반복되어 종료합니다.` |
| 4. EVENT consumer 부재 | `watch.sh를 띄웠습니다. EVENT가 발생하면 처리하겠습니다.` (단, 본 turn 안에서 case 분기 없음) |

근본 원인은 모두 동일하다 — 호출자가 polling을 외부 알림에 위임할 수 있다고 잘못 판단하고 자기 turn을 종료하는 것. 본 스킬에는 외부 알림 경로가 존재하지 않으며(§"절대 명령" + §원칙), 모든 진행은 호출자의 포그라운드 `watch.sh` 단일 호출 + 같은 turn 안 case 분기로만 이루어진다. 위 시그널이 나타나려 하면 메시지를 출력하지 말고 즉시 `watch.sh`를 호출하여 polling을 재개한다 — `watch.sh`는 단일 Bash 호출 안에서 무한 루프를 돌므로 호출자가 자기 turn을 자발적으로 종료할 구조적 여지가 없다.

## 종료 조건

`mergeState in (CLEAN, UNSTABLE)` + `pendingChecks=0` + `failedChecks=0` → Phase 7 전환. GitHub Copilot code review는 formal Approve를 남기지 않으므로 `reviewDecision=APPROVED`를 요구하지 않는다. 실제 branch protection상 human approval이 필수라면 GitHub가 `mergeState=BLOCKED`로 노출한다.

$ARGUMENTS
