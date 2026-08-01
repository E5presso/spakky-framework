#!/usr/bin/env bash
# REVIEW_BOT_LOGINS and negative-review regression coverage for the bot-head gates.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
watch_sh="$script_dir/watch.sh"

run_case() {
  local case_name="$1" configured_logins="$2" author_login="$3" channel="$4"
  local review_state="$5" merge_state="$6" review_decision="$7" expected_reason="$8"
  local require_bot_head_eval="${9:-1}"
  local has_auto_approvable="${10:-0}"
  local tmp_dir head_oid head_commit_date review_date ch2_json ch3_json prev_ch2 prev_ch3 labels_json

  tmp_dir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp_dir'" RETURN
  head_oid="abc123def456"
  head_commit_date="2026-01-01T00:00:00Z"
  review_date="2026-01-01T01:00:00Z"
  ch2_json='[]'
  ch3_json='[]'
  prev_ch2='{}'
  prev_ch3='{}'
  labels_json='[]'

  if [ "$has_auto_approvable" = "1" ]; then
    labels_json='[{"name":"auto-approvable"}]'
  fi

  case "$channel" in
    ch2)
      ch2_json="[{\"id\":201,\"user\":{\"login\":\"$author_login\"},\"created_at\":\"$review_date\",\"updated_at\":\"$review_date\",\"body\":\"reviewed\"}]"
      prev_ch2="{\"201\":\"$review_date\"}"
      ;;
    ch3)
      ch3_json="[{\"id\":301,\"user\":{\"login\":\"$author_login\"},\"submitted_at\":\"$review_date\",\"commit_id\":\"$head_oid\",\"state\":\"$review_state\",\"body\":\"reviewed\"}]"
      prev_ch3="{\"301\":\"$review_date\"}"
      ;;
    ch3_mixed_heads)
      ch3_json="[{\"id\":301,\"user\":{\"login\":\"review-app-a[bot]\"},\"submitted_at\":\"2026-01-01T01:00:00Z\",\"commit_id\":\"$head_oid\",\"state\":\"COMMENTED\",\"body\":\"reviewed head\"},{\"id\":302,\"user\":{\"login\":\"review-app-b[bot]\"},\"submitted_at\":\"2026-01-01T02:00:00Z\",\"commit_id\":\"stale123\",\"state\":\"COMMENTED\",\"body\":\"reviewed stale head\"}]"
      prev_ch3='{"301":"2026-01-01T01:00:00Z","302":"2026-01-01T02:00:00Z"}'
      ;;
    none) ;;
  esac

  mkdir -p "$tmp_dir/bin"
  cat > "$tmp_dir/bin/gh" <<EOF_GH
#!/usr/bin/env bash
set -euo pipefail

cmd="\$1"
shift || true
if [ "\$cmd" = "pr" ] && [ "\${1:-}" = "view" ]; then
  cat <<'EOJSON'
{
  "mergeStateStatus": "$merge_state",
  "reviewDecision": "$review_decision",
  "statusCheckRollup": [
    {"name":"ci","status":"COMPLETED","conclusion":"SUCCESS","workflowName":"ci"}
  ],
  "comments": [],
  "state": "OPEN",
  "headRefOid": "$head_oid",
  "labels": $labels_json
}
EOJSON
  exit 0
fi

if [ "\$cmd" = "api" ]; then
  endpoint="\$1"
  shift
  jq_filter=""
  while [ \$# -gt 0 ]; do
    case "\$1" in
      --jq) jq_filter="\$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  case "\$endpoint" in
    *"/pulls/"*"/comments") echo '[]' ;;
    *"/issues/"*"/comments") echo '$ch2_json' ;;
    *"/pulls/"*"/reviews") echo '$ch3_json' ;;
    *"/commits/"*)
      if [ -n "\$jq_filter" ]; then
        echo "$head_commit_date"
      else
        echo '{"commit":{"committer":{"date":"$head_commit_date"}}}'
      fi
      ;;
    *) exit 1 ;;
  esac
  exit 0
fi
exit 1
EOF_GH
  chmod +x "$tmp_dir/bin/gh"

  cat > "$tmp_dir/bin/sleep" <<'EOF_SLEEP'
#!/usr/bin/env bash
exit 0
EOF_SLEEP
  chmod +x "$tmp_dir/bin/sleep"

  cat > "$tmp_dir/prev_state.json" <<EOF_STATE
{"ch1":{},"ch2":$prev_ch2,"ch3":$prev_ch3,"reviewDecision":"$review_decision"}
EOF_STATE

  grep -v '^export PATH="/opt/homebrew/bin' "$watch_sh" > "$tmp_dir/watch_under_test.sh"
  MONITOR_PR_SCRIPTS_DIR="$script_dir" \
    PATH="$tmp_dir/bin:/usr/bin:/bin" \
    REVIEW_BOT_LOGINS="$configured_logins" \
    REQUIRE_REVIEW_BOT_HEAD_EVAL="$require_bot_head_eval" \
    REPO=E5presso/spakky-framework \
    PR_NUMBER=99999 \
    PREV_STATE_FILE="$tmp_dir/prev_state.json" \
    bash "$tmp_dir/watch_under_test.sh" > "$tmp_dir/stdout.log" 2> "$tmp_dir/stderr.log" || true

  if ! grep -q "^reason=$expected_reason$" "$tmp_dir/stdout.log"; then
    echo "FAIL [$case_name]: expected reason=$expected_reason" >&2
    cat "$tmp_dir/stdout.log" >&2
    cat "$tmp_dir/stderr.log" >&2
    return 1
  fi
  echo "OK [$case_name]: reason=$expected_reason"
}

run_case "default-commented" "" "claude[bot]" ch3 COMMENTED CLEAN REVIEW_REQUIRED mergeable-clean
run_case "configured-preserves-default" "review-app[bot]" "claude[bot]" ch3 COMMENTED CLEAN REVIEW_REQUIRED mergeable-clean
run_case "configured-commented" "  review-app[bot]  " "review-app[bot]" ch3 COMMENTED CLEAN REVIEW_REQUIRED mergeable-clean
run_case "configured-list-second-login" "review-app-a[bot],review-app-b[bot]" "review-app-b[bot]" ch3 COMMENTED CLEAN REVIEW_REQUIRED mergeable-clean
run_case "configured-multiple-bots-any-exact-head" "review-app-a[bot],review-app-b[bot]" "" ch3_mixed_heads COMMENTED CLEAN REVIEW_REQUIRED mergeable-clean
run_case "configured-approved" "review-app[bot]" "review-app[bot]" ch3 APPROVED CLEAN APPROVED mergeable-clean
run_case "configured-changes-requested-state" "review-app[bot]" "review-app[bot]" ch3 CHANGES_REQUESTED CLEAN REVIEW_REQUIRED mergeable-clean
run_case "configured-changes-requested" "review-app[bot]" "review-app[bot]" ch3 CHANGES_REQUESTED BLOCKED CHANGES_REQUESTED awaiting-human-review
run_case "configured-changes-requested-clean" "review-app[bot]" "review-app[bot]" ch3 CHANGES_REQUESTED CLEAN CHANGES_REQUESTED awaiting-human-review
run_case "disabled-bot-gate-changes-requested-clean" "" "" none CHANGES_REQUESTED CLEAN CHANGES_REQUESTED awaiting-human-review 0
run_case "disabled-bot-gate-changes-requested-unstable" "" "" none CHANGES_REQUESTED UNSTABLE CHANGES_REQUESTED awaiting-human-review 0
run_case "labeled-changes-requested-blocked" "" "" none CHANGES_REQUESTED BLOCKED CHANGES_REQUESTED awaiting-human-review 1 1
run_case "labeled-changes-requested-behind" "" "" none CHANGES_REQUESTED BEHIND CHANGES_REQUESTED awaiting-human-review 1 1
run_case "blocked-review-required-needs-bot-evidence" "" "" none COMMENTED BLOCKED REVIEW_REQUIRED heartbeat
run_case "behind-review-required-needs-bot-evidence" "" "" none COMMENTED BEHIND REVIEW_REQUIRED heartbeat
run_case "configured-ch2" "review-app[bot]" "review-app[bot]" ch2 COMMENTED BLOCKED REVIEW_REQUIRED awaiting-human-review
run_case "ch3-exact-login-match" "review-app[bot]" "review-app[bot]-shadow" ch3 COMMENTED BLOCKED REVIEW_REQUIRED heartbeat
run_case "ch2-exact-login-match" "review-app[bot]" "review-app[bot]-shadow" ch2 COMMENTED BLOCKED REVIEW_REQUIRED heartbeat

echo "test_review_bot_logins.sh: OK"
