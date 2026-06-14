#!/usr/bin/env bash
# PR 상태를 30초 주기로 polling하며 "이벤트 발생" 또는 "종료 조건"까지 단일 Bash 호출 안에서 블록한다.
# poll.sh의 단일 스냅샷 변형이 "에이전트가 매 cycle 자기 turn 안에서 재호출"을 요구하여
# 서브에이전트 컨텍스트에서 turn 종료(조기 exit)를 야기하는 패턴을 차단한다.
#
# 본 스크립트는 포그라운드 Bash tool 1회 호출 안에서 무한 루프를 돌며,
# 다음 중 하나가 관찰되면 EVENT 또는 DONE 행을 출력하고 종료한다 — 호출자(에이전트)는 한 번의 Bash 호출만으로
# turn을 점유하므로 "백그라운드 알림 수신"으로 자기 turn을 종료할 여지가 없다.
#
# 사용법:
#   REPO=E5presso/spakky-framework PR_NUMBER=23504 bash watch.sh
#
# 환경변수 (선택):
#   PREV_STATE_FILE
#     — 직전 cycle에 관찰된 코멘트/리뷰의 (id, updatedAt) 페어 + reviewDecision 캐시 파일 경로.
#       JSON 스키마: {"ch1": {"<id>": "<updatedAt>", ...}, "ch2": {...}, "ch3": {...}, "reviewDecision": "<X>"}
#       파일이 없거나 비어 있으면 첫 cycle을 baseline으로 채워 다음 변화부터 EVENT로 보고한다.
#       매 cycle 종료 시 현재 스냅샷으로 덮어쓴다. reviewDecision baseline도 본 파일에 영속되므로
#       호출자는 직전 값을 별도 환경변수로 전달할 필요가 없다 — 코멘트 3채널과 동일하게 상태 파일로 일원화.
#   INTERRUPT_FILE
#     — 메인 세션이 모니터링 중 호출자에게 SendMessage 로 지시를 보낼 때 그 직후 쓰는 sentinel 파일 경로
#       (관례상 워크트리 루트의 .monitor-interrupt). 매 cycle sleep 직후 존재를 확인하여, 있으면 삭제 후
#       EVENT reason=interrupt 로 즉시 종료한다. 미지정 시 본 경로 비활성. 상세는 아래 "interrupt:" 주석.
#
# 출력 형식 (마지막 1회만 출력 후 종료):
#   - 종료 조건 도달:
#       DONE
#       mergeState=<X>
#       reviewDecision=<Y>
#       commentCount=<N>
#       reviewCommentCount=<N>
#       failedChecks=0
#       reason=<merged|mergeable-clean|closed-without-merge|awaiting-human-review>
#   - 이벤트 발생 (호출자가 분기 처리 후 재호출 필요):
#       EVENT
#       mergeState=<X>
#       reviewDecision=<Y>
#       commentCount=<N>
#       reviewCommentCount=<N>
#       failedChecks=<N>
#       reason=<comments-changed|review-decision-changed|ci-failed|merge-dirty|bot-stuck|heartbeat|interrupt>
#       staleHandledIds=<id1,id2,...>   # reason=comments-changed 일 때만, in-place 갱신된 id 목록 (없으면 빈 값)
#
# heartbeat: 변화 없는 cycle이 8회(=240초) 누적되면 1회 송신하여 호출자가 SendMessage tick ping을 송신하도록
#   유도한다. 메인 세션이 sub-agent를 hang으로 오판하지 않게 하는 가시성 장치이자, 모델이 prompt-cache TTL(300초)
#   안에 1회 샘플링하여 캐시를 cold write가 아닌 read로 갱신하게 하는 비용 장치다. 호출자는 즉시 watch.sh를
#   다시 호출하여 polling을 재개한다 (cycle 카운터는 새 호출에서 0부터 재시작).
#
# interrupt: 메인 세션(orchestrator)이 모니터링 중인 호출자에게 SendMessage 로 지시를 보낼 때 그 직후
#   INTERRUPT_FILE 경로에 sentinel 파일을 쓴다. 본 스크립트는 30초 cycle 의 sleep 을 1초 단위로 쪼개
#   매초 sentinel 존재를 확인하고, 있으면 즉시 삭제한 뒤 EVENT reason=interrupt 를 emit하고 종료한다
#   (감지 지연 <=1초). 호출자는 이 EVENT 를 받고 turn 을 종료하며, turn 종료 시점에 비로소 큐의
#   SendMessage 가 호출자 inbox 로 배달되어 호출자를 새 turn 으로 깨운다 (호출자 측 처리는 monitor-pr
#   SKILL.md §"Interrupt — 능동 지시 yield"). heartbeat(240초)만으로는 능동 지시 배달이 최대 240초 지연되므로
#   본 경로가 그 지연을 수 초 이내로 단축한다. sentinel 소비(삭제)는 본 스크립트 책임이며 재호출 시 즉시
#   재인터럽트되지 않는다 (idempotent trigger). INTERRUPT_FILE 미지정 시 본 경로는 비활성.
#
# `staleHandledIds` 는 이전 cycle 캐시에 존재했지만 `updatedAt`이 증가한 row의 id 목록이다.
# 호출자(에이전트)는 이 값을 `collect_comments.sh`의 `STALE_HANDLED_IDS` 환경변수로 그대로 전달하여
# 해당 id의 기존 reply 마커를 무효화하고 변경된 본문을 재수집·재triage한다.
#
# bot-stuck: claude bot이 마지막 리뷰 이후 신규 커밋이 없어 재리뷰를 트리거하지 않는 정체 상태.
#   AND 조건: (a) 모든 CI check가 COMPLETED (PENDING/IN_PROGRESS 0건), (b) mergeState != CLEAN,
#   (c) reviewDecision != APPROVED, (d) latest claude[bot] review.commit.oid != HEAD oid (또는 review 부재),
#   (e) bot_evaluated_head == 0 (봇이 HEAD 를 평가하지 않았다), (f) PR labels 에 "auto-approvable" 포함.
#   호출자는 빈 커밋 push로 새 commit hash를 만들어 봇 재리뷰 + CI 재실행을 유도한다 (SKILL.md 참조).
#   상한 1회는 호출자가 .process-state.json으로 누적·검사한다 (스크립트는 무상태).
#
#   (f) 의 의의: "auto-approvable" 태그는 pr-review SKILL.md 가 AE6/AE7 또는 전 파일 AE1–AE5 매칭 시
#   `gh pr edit --add-label "auto-approvable"` 로 자동 부여한다 — 봇이 자동 승인 가능 요건을 갖췄음을
#   의미한다. 태그가 없는 PR 은 휴먼 리뷰가 정상 경로이므로 stuck 으로 간주하지 않는다 (retrigger 시도가
#   휴먼 리뷰 대기 PR 에서 무의미한 빈 커밋만 누적시키는 회귀 차단).
#
# awaiting-human-review (terminal DONE): claude bot 이 HEAD 를 평가했고 의도적으로 승인하지 않은 상태.
#   봇 재평가 트리거가 부재하므로 polling 누적이 무의미하다 — DONE 으로 종료하여 호출자(서브에이전트)가
#   status=awaiting-review 로 보고 후 turn 종료.
#   bot_evaluated_head 의 두 경로 (OR): (1) latest_bot_ch2_date > head_commit_date (CH2 issue comment),
#   (2) latest_bot_review_oid == head_oid AND latest_bot_review_state == "COMMENTED" (CH3 reviews API).
#   AND 조건: (a) pending_checks == 0, (b) failed_checks == 0, (c) mergeState in {BLOCKED, BEHIND}
#   (DIRTY 제외 — DIRTY 는 EVENT 로 별도 분기), (d) reviewDecision != APPROVED, (e) bot_evaluated_head == 1.
#   분기 위치: 모든 EVENT 분기 이후 (변화 있으면 EVENT 우선) + heartbeat 직전 (변화 없음 path 에서 즉시 종료).
#
# 매 30초 cycle마다 stderr에 1줄 진행 로그를 출력한다 (살아있음 가시성):
#   [watch.sh] <ISO-8601 ts> mergeState=<X> reviewDecision=<Y> comments=<N> reviewComments=<N> failed=<N>
#
# 무한 루프이지만 백그라운드가 아닌 "단일 Bash tool 호출의 포그라운드 점유" — Monitor 도구·run_in_background·
# ScheduleWakeup·CronCreate가 아니다. 호출자의 turn은 본 스크립트가 종료할 때까지 차단된다.
set -euo pipefail

export PATH="/opt/homebrew/bin:$PATH"

if ! command -v gh >/dev/null 2>&1; then
  echo "FATAL: gh CLI not found in PATH ($PATH)" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "FATAL: jq not found in PATH ($PATH)" >&2
  exit 1
fi

: "${REPO:?REPO env required}"
: "${PR_NUMBER:?PR_NUMBER env required}"

prev_state_file="${PREV_STATE_FILE:-}"
interrupt_file="${INTERRUPT_FILE:-}"

# Load prev state map from file (or empty if absent).
# baseline_done: 첫 cycle 이후 1로 set. 코멘트 0개·reviewDecision null PR에서도 baseline init이
# 반복되어 EVENT(ci-failed·bot-stuck 등) 누락되는 회귀를 차단한다.
# reviewDecision baseline은 코멘트 3채널과 동일하게 상태 파일에서 로드한다 — 환경변수 미전달 시
# prev_review_decision=""로 시작하여 매 cycle false review-decision-changed가 발생하던 회귀를 차단.
if [ -n "$prev_state_file" ] && [ -s "$prev_state_file" ]; then
  prev_state=$(cat "$prev_state_file")
  prev_review_decision=$(echo "$prev_state" | jq -r '.reviewDecision // ""')
  baseline_done=1
else
  prev_state='{"ch1":{},"ch2":{},"ch3":{},"reviewDecision":""}'
  prev_review_decision=""
  baseline_done=0
fi

# cycle 카운터 — 변화 없음 cycle이 누적되면 heartbeat 송신 트리거.
# 8 cycle × 30s = 240초 — prompt-cache TTL(300초) 이내로 잡아 대기 중 모델 1회 샘플링이
# 캐시를 cold write가 아닌 read로 갱신하게 한다 (TTL 초과 시 전체 컨텍스트 cold 재기록).
# 본 호출 안에서만 카운트 (호출자가 EVENT 수신 후 재호출 시 0부터 재시작).
no_change_cycles=0
heartbeat_cycle_threshold=8

snapshot_and_emit() {
  local marker="$1" reason="$2" stale_ids="${3:-}"
  echo "$marker"
  echo "mergeState=$merge_state"
  echo "reviewDecision=$review_decision"
  echo "commentCount=$comment_count"
  echo "reviewCommentCount=$review_comment_count"
  echo "failedChecks=$failed_checks"
  echo "reason=$reason"
  if [ "$reason" = "comments-changed" ]; then
    echo "staleHandledIds=$stale_ids"
  fi
}

# Detect (id, updatedAt) drift between prev_state and current_state.
# 출력: 공백 구분 id 목록 — 직전 캐시에 존재했고 updatedAt이 증가한 id (= in-place 갱신).
diff_stale_ids() {
  local prev="$1" curr="$2"
  jq -r -n --argjson prev "$prev" --argjson curr "$curr" '
    [ ("ch1","ch2","ch3") as $ch
      | ($curr[$ch] // {}) | to_entries[]
      | . as $e
      | ($prev[$ch][$e.key]) as $prev_at
      | select($prev_at != null and $e.value > $prev_at)
      | $e.key
    ]
    | join(",")
  '
}

# 신규 id 존재 여부 (이전 캐시에 없던 id).
has_new_ids() {
  local prev="$1" curr="$2"
  jq -r -n --argjson prev "$prev" --argjson curr "$curr" '
    [ ("ch1","ch2","ch3") as $ch
      | ($curr[$ch] // {}) | keys[]
      | . as $k
      | select(($prev[$ch] // {}) | has($k) | not)
    ]
    | length > 0
  '
}

while true; do
  # interrupt-aware sleep: 30초 cycle 간격을 1초 단위로 쪼개 매초 sentinel 을 확인한다.
  # gh 스냅샷 polling 주기는 30초 그대로 — sleep 만 잘게 쪼개 interrupt 감지 지연을
  # <=1초로 줄인다. sentinel 존재 시 gh API 호출 전에 즉시 종료하여 호출자 turn 을
  # yield시킨다. 소비(삭제)는 본 스크립트 책임 (idempotent). 헤더 주석 "interrupt:" 참조.
  interrupted=0
  for _ in $(seq 30); do
    sleep 1
    if [ -n "$interrupt_file" ] && [ -f "$interrupt_file" ]; then
      interrupted=1
      break
    fi
  done
  if [ "$interrupted" -eq 1 ]; then
    rm -f "$interrupt_file"
    echo "EVENT"
    echo "reason=interrupt"
    exit 0
  fi

  snapshot=$(gh pr view "$PR_NUMBER" --repo "$REPO" \
    --json mergeStateStatus,reviewDecision,statusCheckRollup,comments,state,headRefOid,labels)
  ch1_raw=$(gh api "repos/$REPO/pulls/$PR_NUMBER/comments" --paginate)
  ch2_raw=$(gh api "repos/$REPO/issues/$PR_NUMBER/comments" --paginate)
  ch3_raw=$(gh api "repos/$REPO/pulls/$PR_NUMBER/reviews" --paginate)

  merge_state=$(echo "$snapshot" | jq -r '.mergeStateStatus // ""')
  review_decision=$(echo "$snapshot" | jq -r '.reviewDecision // ""')
  pr_state=$(echo "$snapshot" | jq -r '.state // ""')
  head_oid=$(echo "$snapshot" | jq -r '.headRefOid // ""')
  comment_count=$(echo "$snapshot" | jq '.comments | length')
  review_comment_count=$(echo "$ch1_raw" | jq 'length')
  # statusCheckRollup 은 GitHub 측에서 CheckRun (`conclusion: SUCCESS|FAILURE|...`) 과
  # StatusContext (`state: SUCCESS|FAILURE|ERROR|PENDING`) 두 형태가 섞여 들어온다. external CI infra
  # 같은 external status 는 StatusContext.state 로 보고되므로 conclusion 만 보면 ERROR/FAILURE 가
  # 누락되어 failedChecks=0 false negative 가 발생한다. 두 형태 모두 catch.
  #
  # 동일 check (예: PR title 재검증 워크플로) 가 재실행되면 rollup 에 옛 run 과 새 run 이 함께 남는다 —
  # 옛 FAILURE run 이 그대로 집계되면 새 SUCCESS 가 들어와도 failedChecks>0 이 영구 고착되어 ci-failed
  # EVENT 가 무한 재발행된다. name/context 로 그룹화하여 startedAt 최신 run 1건만 평가한다.
  latest_checks=$(echo "$snapshot" | jq -c '[
    .statusCheckRollup // []
    | group_by(.name // .context)
    | .[]
    | sort_by(.startedAt // .completedAt // "") | last
  ]')
  failed_checks=$(echo "$latest_checks" | jq '[.[] | select(((.conclusion == "FAILURE" or .conclusion == "ERROR") or (.state == "FAILURE" or .state == "ERROR")) and (.workflowName != "Auto PR Code Review"))] | length')
  pending_checks=$(echo "$latest_checks" | jq '[.[] | select(.status != "COMPLETED" and .status != null)] | length')
  has_auto_approvable=$(echo "$snapshot" | jq '[.labels // [] | .[] | select(.name == "auto-approvable")] | length > 0')

  # latest claude[bot] review의 commit.oid / state (없으면 빈 문자열)
  latest_bot_review_oid=$(echo "$ch3_raw" \
    | jq -r '[.[] | select(.user.login == "claude[bot]")] | sort_by(.submitted_at) | last | .commit_id // ""' 2>/dev/null || echo "")
  latest_bot_review_state=$(echo "$ch3_raw" \
    | jq -r '[.[] | select(.user.login == "claude[bot]")] | sort_by(.submitted_at) | last | .state // ""' 2>/dev/null || echo "")

  # HEAD commit의 committedDate (없으면 빈 문자열) — claude[bot] 평가 시점 비교용
  head_commit_date=$(gh api "repos/$REPO/commits/$head_oid" \
    --jq '.commit.committer.date // ""' 2>/dev/null || echo "")

  # latest claude[bot] CH2 issue comment의 created_at (없으면 빈 문자열).
  # claude[bot]이 자동 승인 비적격 판정 시 formal review 대신 issue comment 로 의견을 남기는 경로 —
  # 이 코멘트가 HEAD 이후에 작성되었다면 봇은 현재 HEAD를 평가한 것으로 간주.
  # claude[bot] edits its CH2 summary comment in-place on re-review: created_at stays at first-post time
  # while updated_at advances. Use max(created_at, updated_at) so an in-place re-review counts as the
  # bot having evaluated the current HEAD — otherwise condition (e) misclassifies awaiting-human-review
  # as bot-stuck and can trigger a credit-burning empty-commit retrigger.
  latest_bot_ch2_date=$(echo "$ch2_raw" \
    | jq -r '[.[] | select(.user.login == "claude[bot]") | (if (.updated_at // "") > (.created_at // "") then .updated_at else .created_at end)] | sort | last // ""' 2>/dev/null || echo "")

  bot_evaluated_head=0
  if [ -n "$latest_bot_ch2_date" ] && [ -n "$head_commit_date" ] \
     && [ "$latest_bot_ch2_date" \> "$head_commit_date" ]; then
    bot_evaluated_head=1
  fi
  if [ -n "$latest_bot_review_oid" ] \
     && [ "$latest_bot_review_oid" = "$head_oid" ] \
     && [ "$latest_bot_review_state" = "COMMENTED" ]; then
    bot_evaluated_head=1
  fi

  # Build current (id -> updated_at) map per channel.
  # CH1 (인라인 리뷰 코멘트), CH2 (일반 PR 코멘트): updated_at 필드 사용.
  # CH3 (리뷰): GitHub Reviews API는 updated_at을 노출하지 않으므로 submitted_at을 baseline으로 쓴다.
  #   리뷰 본문 in-place 갱신은 GraphQL 또는 reactions 변화로만 관찰 가능 — 본 스킬 범위 밖.
  #   in-place 갱신은 주로 CH1/CH2에서 발생 (claude bot 코멘트/인라인 코멘트).
  curr_state=$(jq -n \
    --argjson ch1 "$ch1_raw" \
    --argjson ch2 "$ch2_raw" \
    --argjson ch3 "$ch3_raw" \
    --arg review_decision "$review_decision" '
    {
      ch1: ($ch1 | map({(.id|tostring): (.updated_at // .created_at)}) | add // {}),
      ch2: ($ch2 | map({(.id|tostring): (.updated_at // .created_at)}) | add // {}),
      ch3: ($ch3 | map({(.id|tostring): (.submitted_at // "")}) | add // {}),
      reviewDecision: $review_decision
    }
  ')

  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "[watch.sh] $ts mergeState=$merge_state reviewDecision=$review_decision comments=$comment_count reviewComments=$review_comment_count failed=$failed_checks" >&2

  # Persist current state for next cycle (after this iteration's emit, regardless of outcome).
  persist_state() {
    if [ -n "$prev_state_file" ]; then
      printf '%s' "$curr_state" > "$prev_state_file"
    fi
  }

  # 종료 조건 1: PR이 이미 머지되었거나 클로즈된 경우
  if [ "$pr_state" = "MERGED" ]; then
    persist_state
    snapshot_and_emit "DONE" "merged"
    exit 0
  fi
  if [ "$pr_state" = "CLOSED" ]; then
    persist_state
    snapshot_and_emit "DONE" "closed-without-merge"
    exit 0
  fi

  # 종료 조건 2: CLEAN/UNSTABLE + CI green + review bot HEAD 평가 완료
  # Codex/Copilot review bots often submit COMMENTED reviews instead of formal APPROVED.
  if { [ "${REQUIRE_REVIEW_BOT_HEAD_EVAL:-1}" = "0" ] || [ "$bot_evaluated_head" = "1" ]; } \
     && { [ "$merge_state" = "CLEAN" ] || [ "$merge_state" = "UNSTABLE" ]; } \
     && [ "$pending_checks" = "0" ] \
     && [ "$failed_checks" = "0" ]; then
    persist_state
    snapshot_and_emit "DONE" "mergeable-clean"
    exit 0
  fi

  # baseline 초기화 (첫 cycle만): 변화 검출 baseline만 채우고 EVENT로 보고하지 않는다.
  # baseline_done 플래그로 한 번만 실행 — 코멘트 0개·reviewDecision=null PR에서 매 cycle 재진입을 차단.
  if [ "$baseline_done" != "1" ]; then
    prev_state="$curr_state"
    prev_review_decision="$review_decision"
    baseline_done=1
    persist_state
    continue
  fi

  # 이벤트 1: CI 실패
  if [ "$failed_checks" -gt 0 ]; then
    persist_state
    snapshot_and_emit "EVENT" "ci-failed"
    exit 0
  fi

  # 이벤트 2: 머지 충돌
  if [ "$merge_state" = "DIRTY" ]; then
    persist_state
    snapshot_and_emit "EVENT" "merge-dirty"
    exit 0
  fi

  # 이벤트 3: 코멘트/리뷰 변화 — 신규 id 또는 in-place 갱신 (updatedAt 증가).
  new_ids=$(has_new_ids "$prev_state" "$curr_state")
  stale_ids=$(diff_stale_ids "$prev_state" "$curr_state")
  if [ "$new_ids" = "true" ] || [ -n "$stale_ids" ]; then
    persist_state
    snapshot_and_emit "EVENT" "comments-changed" "$stale_ids"
    exit 0
  fi

  # 이벤트 4: 리뷰 결정 변경
  if [ "$review_decision" != "$prev_review_decision" ]; then
    persist_state
    snapshot_and_emit "EVENT" "review-decision-changed"
    exit 0
  fi

  # 이벤트 5: bot-stuck — claude bot이 신규 커밋을 인식하지 않아 재리뷰 트리거가 누락된 정체 상태.
  # (a) CI 전부 COMPLETED, (b) mergeState != CLEAN, (c) reviewDecision != APPROVED,
  # (d) latest claude[bot] review.commit_id != HEAD oid (또는 review 부재),
  # (e) 동시에 봇이 HEAD 를 평가하지 않았다 (bot_evaluated_head=0),
  # (f) PR labels 에 "auto-approvable" 포함 (휴먼 리뷰 대기 PR 회복 시도 차단).
  #
  # bot_evaluated_head 의 의의: claude bot 은 자동 승인 비적격 판정 시 두 경로로 의견을 남길 수 있다 —
  # (1) CH2 issue comment 로 "팀원 리뷰 필요" 의견 (HEAD commit 이후 created_at),
  # (2) CH3 reviews API 로 state=COMMENTED 리뷰 (commit_id == HEAD, APPROVED 아님).
  # 둘 중 어느 경로든 봇은 현재 HEAD 를 평가했지만 의도적으로 승인하지 않은 것이므로 stuck 이 아니다 —
  # 빈 커밋 retrigger 는 동일 판정을 재발행할 뿐이며 폴링/크레딧만 소진한다.
  #
  # (f) auto-approvable 태그의 의의: pr-review SKILL.md 가 AE6/AE7 또는 전 파일 AE1–AE5 매칭 시
  # `gh pr edit --add-label "auto-approvable"` 로 자동 부여한다. 태그가 없으면 봇 자동 승인 비적격이며
  # 휴먼 리뷰가 정상 경로 — retrigger 시도는 빈 커밋만 누적시켜 무의미하다.
  if [ "$pending_checks" = "0" ] \
     && [ "$merge_state" != "CLEAN" ] \
     && [ "$review_decision" != "APPROVED" ] \
     && [ "$latest_bot_review_oid" != "$head_oid" ] \
     && [ "$bot_evaluated_head" = "0" ] \
     && [ "$has_auto_approvable" = "true" ]; then
    snapshot_and_emit "EVENT" "bot-stuck"
    exit 0
  fi

  # 종료 조건 3: awaiting-human-review — 봇이 HEAD 를 평가했으나 review submission 대신 CH2 코멘트로
  # 휴먼 리뷰 의견을 남긴 상태. bot_evaluated_head=1 가드로 bot-stuck EVENT 가 의도적으로 미송신되는
  # 케이스에서, 추가 polling 은 봇 재평가 트리거 부재 + 휴먼 리뷰만 남음 = 무의미 — DONE 으로 종료한다.
  # 본 분기는 모든 EVENT 분기 이후에 위치하므로 변화가 있으면 EVENT 가 먼저 종료, 변화 없음 path 에서만
  # 본 DONE 이 송신된다 (heartbeat 누적 직전).
  if [ "$pending_checks" = "0" ] \
     && [ "$failed_checks" = "0" ] \
     && { [ "$merge_state" = "BLOCKED" ] || [ "$merge_state" = "BEHIND" ]; } \
     && [ "$review_decision" != "APPROVED" ] \
     && [ "$bot_evaluated_head" = "1" ]; then
    persist_state
    snapshot_and_emit "DONE" "awaiting-human-review"
    exit 0
  fi

  # 변화 없음 — heartbeat 카운터 증가, 임계 도달 시 EVENT reason=heartbeat 송신.
  no_change_cycles=$((no_change_cycles + 1))
  prev_state="$curr_state"
  prev_review_decision="$review_decision"
  persist_state
  if [ "$no_change_cycles" -ge "$heartbeat_cycle_threshold" ]; then
    snapshot_and_emit "EVENT" "heartbeat"
    exit 0
  fi
done
