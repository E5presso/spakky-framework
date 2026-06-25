#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '%s\n' "$*" >&2
}

set_output() {
  local name="$1"
  local value="$2"

  if [ -n "${GITHUB_STEP_OUTPUT:-}" ]; then
    printf '%s=%s\n' "$name" "$value" >> "$GITHUB_STEP_OUTPUT"
  fi
}

no_approve() {
  local reason="$1"

  log "ai-review auto-approve: no-op reason=$reason"
  set_output "approved" "false"
  set_output "reason" "$reason"
  exit 0
}

require_env() {
  local name="$1"

  if [ -z "${!name:-}" ]; then
    log "ai-review auto-approve: missing required env $name"
    exit 2
  fi
}

require_env "REPO"
require_env "STATUS_SHA"
require_env "STATUS_CONTEXT"
require_env "STATUS_STATE"

if [ "$STATUS_CONTEXT" != "ai-review" ]; then
  no_approve "context-not-ai-review"
fi

if [ "$STATUS_STATE" != "success" ]; then
  no_approve "state-not-success"
fi

pulls_json=$(gh api \
  -H "Accept: application/vnd.github+json" \
  "repos/$REPO/commits/$STATUS_SHA/pulls")

matching_pr_count=$(jq --arg sha "$STATUS_SHA" '
  [.[] | select(.state == "open" and .head.sha == $sha)] | length
' <<<"$pulls_json")

if [ "$matching_pr_count" -eq 0 ]; then
  no_approve "no-open-pr-for-status-sha"
fi

if [ "$matching_pr_count" -gt 1 ]; then
  no_approve "ambiguous-open-prs-for-status-sha"
fi

pr_number=$(jq -r --arg sha "$STATUS_SHA" '
  [.[] | select(.state == "open" and .head.sha == $sha)] | first | .number
' <<<"$pulls_json")

pull_json=$(gh api "repos/$REPO/pulls/$pr_number")
head_sha=$(jq -r '.head.sha // ""' <<<"$pull_json")
head_repo=$(jq -r '.head.repo.full_name // ""' <<<"$pull_json")
base_repo=$(jq -r '.base.repo.full_name // ""' <<<"$pull_json")

if [ "$head_sha" != "$STATUS_SHA" ]; then
  no_approve "stale-status"
fi

if [ "$head_repo" != "$base_repo" ]; then
  no_approve "fork-pr"
fi

statuses_json=$(gh api "repos/$REPO/commits/$STATUS_SHA/statuses")
latest_status=$(jq -c --arg context "$STATUS_CONTEXT" '
  [.[] | select(.context == $context)] | sort_by(.created_at) | last // empty
' <<<"$statuses_json")

if [ -z "$latest_status" ]; then
  no_approve "ai-review-status-not-found"
fi

latest_state=$(jq -r '.state // ""' <<<"$latest_status")
creator_login=$(jq -r '.creator.login // ""' <<<"$latest_status")

if [ "$latest_state" != "success" ]; then
  no_approve "latest-ai-review-status-not-success"
fi

if [ -z "$creator_login" ]; then
  no_approve "ai-review-status-creator-missing"
fi

if ! permission_json=$(gh api "repos/$REPO/collaborators/$creator_login/permission"); then
  no_approve "creator-permission-unavailable"
fi

creator_role=$(jq -r '.role_name // ""' <<<"$permission_json")

case "$creator_role" in
  admin | maintain) ;;
  *) no_approve "creator-role-not-admin-or-maintain" ;;
esac

reviews_json=$(gh api "repos/$REPO/pulls/$pr_number/reviews")
already_approved_count=$(jq --arg sha "$STATUS_SHA" '
  [
    .[]
    | select(.user.login == "github-actions[bot]")
    | select(.state == "APPROVED")
    | select((.commit_id // "") == $sha)
  ]
  | length
' <<<"$reviews_json")

if [ "$already_approved_count" -gt 0 ]; then
  no_approve "already-approved-by-bot"
fi

review_body=$(cat <<EOF_REVIEW_BODY
ai-review status success verified for ${STATUS_SHA}.

- status creator: @${creator_login}
- creator role: ${creator_role}
- provenance: same repository
- staleness: PR head SHA matches status SHA
EOF_REVIEW_BODY
)

if [ "${AI_REVIEW_DRY_RUN:-false}" = "true" ]; then
  log "ai-review auto-approve: dry-run pr=$pr_number sha=$STATUS_SHA creator=$creator_login role=$creator_role"
  set_output "dry_run" "true"
else
  gh pr review "$pr_number" \
    --repo "$REPO" \
    --approve \
    --body "$review_body"
fi

log "ai-review auto-approve: approved pr=$pr_number sha=$STATUS_SHA creator=$creator_login role=$creator_role"
set_output "approved" "true"
set_output "reason" "approved"
set_output "pr_number" "$pr_number"
set_output "creator" "$creator_login"
set_output "creator_role" "$creator_role"
