#!/usr/bin/env bash
# Keep review delegation bound to the canonical review-code context assets.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
review_skill="$repo_root/.agents/skills/review-code/SKILL.md"
review_persona_root="$repo_root/.agents/skills/review-code"
autopilot_wave="$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md"
process_skill="$repo_root/.agents/skills/process-ticket/SKILL.md"
process_phase3="$repo_root/.agents/skills/process-ticket/phases/phase-3-worktree.md"
process_phase4="$repo_root/.agents/skills/process-ticket/phases/phase-4-review.md"
process_phase5="$repo_root/.agents/skills/process-ticket/phases/phase-5-commit.md"
pr_review_skill="$repo_root/.agents/skills/pr-review/SKILL.md"
review_path_classifier="$repo_root/.agents/skills/autopilot/scripts/classify_review_paths.py"
review_mode_resolver="$repo_root/.agents/skills/pr-review/scripts/resolve_review_mode.py"
review_receipt_script="$repo_root/.agents/skills/process-ticket/scripts/review_receipt.py"
autopilot_marker_start='<!-- review-delegate-persona-source:start -->'
autopilot_marker_end='<!-- review-delegate-persona-source:end -->'
zero_file_marker_start='<!-- deterministic-zero-file-short-circuit:start -->'
zero_file_marker_end='<!-- deterministic-zero-file-short-circuit:end -->'
final_delegate_marker_start='<!-- final-review-delegate-contract:start -->'
final_delegate_marker_end='<!-- final-review-delegate-contract:end -->'
final_handler_marker_start='<!-- final-review-handler-contract:start -->'
final_handler_marker_end='<!-- final-review-handler-contract:end -->'
process_resume_marker_start='<!-- publication-resume-contract:start -->'
process_resume_marker_end='<!-- publication-resume-contract:end -->'
autopilot_resume_marker_start='<!-- publication-resume-handler:start -->'
autopilot_resume_marker_end='<!-- publication-resume-handler:end -->'
manual_mode_marker_start='<!-- pr-review-mode-contract:start -->'
manual_mode_marker_end='<!-- pr-review-mode-contract:end -->'
rehydrate_marker_start='<!-- final-review-resume-rehydrate:start -->'
rehydrate_marker_end='<!-- final-review-resume-rehydrate:end -->'
phase5_resume_marker_start='<!-- phase5-resume-contract:start -->'
phase5_resume_marker_end='<!-- phase5-resume-contract:end -->'
identity_producer_marker_start='<!-- review-identity-producer-contract:start -->'
identity_producer_marker_end='<!-- review-identity-producer-contract:end -->'

failures=0

fail() {
  printf 'review-delegate context contract: %s\n' "$1" >&2
  failures=$((failures + 1))
}

for required_file in \
  "$review_skill" \
  "$autopilot_wave" \
  "$process_skill" \
  "$process_phase3" \
  "$process_phase4" \
  "$process_phase5" \
  "$pr_review_skill" \
  "$review_path_classifier" \
  "$review_mode_resolver" \
  "$review_receipt_script"; do
  if [ ! -f "$required_file" ]; then
    fail "missing required contract file: ${required_file#"$repo_root/"}"
  fi
done
if [ "$failures" -ne 0 ]; then
  exit 1
fi

marker_block() {
  local file="$1"
  local start="$2"
  local end="$3"
  awk -v start="$start" -v end="$end" '
    $0 == start { capture = 1; next }
    $0 == end { capture = 0; exit }
    capture { print }
  ' "$file"
}

require_single_marker_pair() {
  local file="$1"
  local start="$2"
  local end="$3"
  local label="$4"
  local start_count
  local end_count
  start_count="$(grep -Fc -- "$start" "$file" || true)"
  end_count="$(grep -Fc -- "$end" "$file" || true)"
  if [ "$start_count" -ne 1 ] || [ "$end_count" -ne 1 ]; then
    fail "$label must have one marker pair"
    return
  fi

  local start_line
  local end_line
  start_line="$(grep -nF -- "$start" "$file" | cut -d: -f1)"
  end_line="$(grep -nF -- "$end" "$file" | cut -d: -f1)"
  if [ "$start_line" -ge "$end_line" ]; then
    fail "$label markers are out of order"
  fi
}

require_block_text() {
  local block="$1"
  local expected="$2"
  local label="$3"
  if ! printf '%s\n' "$block" | grep -Fq -- "$expected"; then
    fail "$label must include: $expected"
  fi
}

marker_start='<!-- review-persona-contract:start -->'
marker_end='<!-- review-persona-contract:end -->'
if [ "$(grep -Fc "$marker_start" "$review_skill" || true)" -ne 1 ] \
  || [ "$(grep -Fc "$marker_end" "$review_skill" || true)" -ne 1 ]; then
  fail "review-code must have one review-persona-contract marker block"
fi

canonical_personas="$(awk -v start="$marker_start" -v end="$marker_end" '
  $0 == start { capture = 1; next }
  $0 == end { capture = 0; exit }
  capture { print }
' "$review_skill" | grep -oE 'personas/[[:alnum:]-]+\.md' | sort -u || true)"
persona_count="$(printf '%s\n' "$canonical_personas" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "$persona_count" -ne 5 ]; then
  fail "review-code must declare exactly five persona paths (found $persona_count)"
fi

for persona_path in $canonical_personas; do
  persona_asset="$review_persona_root/$persona_path"
  if [ ! -f "$persona_asset" ]; then
    fail "missing canonical persona asset: $persona_path"
    continue
  fi

  persona_rules="$(grep -oE '\.agents/rules/[[:alnum:]_.-]+\.md' "$persona_asset" \
    | sort -u || true)"
  if [ -z "$persona_rules" ]; then
    fail "canonical persona cites no rule assets: $persona_path"
  fi
  for rule_path in $persona_rules; do
    if [ ! -f "$repo_root/$rule_path" ]; then
      fail "missing rule asset cited by $persona_path: $rule_path"
    fi
  done
done

category_section="$(awk '
  /^## 의문점 카테고리/ { capture = 1; next }
  capture && /^---$/ { exit }
  capture { print }
' "$review_skill")"
category_count="$(printf '%s\n' "$category_section" | grep -Ec '^\| [0-9]+ \|' || true)"
if [ "$category_count" -ne 14 ]; then
  fail "review-code must map exactly 14 review categories (found $category_count)"
fi

category_number=1
while [ "$category_number" -le 14 ]; do
  category_row="$(printf '%s\n' "$category_section" \
    | grep -E "^\\|[[:space:]]*$category_number[[:space:]]*\\|" || true)"
  category_row_count="$(printf '%s\n' "$category_row" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$category_row_count" -ne 1 ]; then
    fail "review category $category_number must have exactly one mapping row"
    category_number=$((category_number + 1))
    continue
  fi

  row_personas="$(printf '%s\n' "$category_row" \
    | grep -oE 'personas/[[:alnum:]-]+\.md' | sort -u || true)"
  row_persona_count="$(printf '%s\n' "$row_personas" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$row_persona_count" -ne 1 ]; then
    fail "category $category_number must reference exactly one canonical persona path"
  elif ! printf '%s\n' "$canonical_personas" | grep -Fxq "$row_personas"; then
    fail "category $category_number references a persona outside the canonical contract"
  fi
  category_number=$((category_number + 1))
done

category_personas="$(printf '%s\n' "$category_section" \
  | grep -oE 'personas/[[:alnum:]-]+\.md' | sort -u || true)"
if [ "$category_personas" != "$canonical_personas" ]; then
  fail "category mapping persona set differs from the canonical declaration"
fi

autopilot_marker_start_count="$(grep -Fc "$autopilot_marker_start" "$autopilot_wave" || true)"
autopilot_marker_end_count="$(grep -Fc "$autopilot_marker_end" "$autopilot_wave" || true)"
if [ "$autopilot_marker_start_count" -ne 1 ] \
  || [ "$autopilot_marker_end_count" -ne 1 ]; then
  fail "autopilot must have one review-delegate persona source marker block"
else
  autopilot_marker_start_line="$(grep -nF "$autopilot_marker_start" "$autopilot_wave" \
    | cut -d: -f1)"
  autopilot_marker_end_line="$(grep -nF "$autopilot_marker_end" "$autopilot_wave" \
    | cut -d: -f1)"
  if [ "$autopilot_marker_start_line" -ge "$autopilot_marker_end_line" ]; then
    fail "autopilot review-delegate persona source markers are out of order"
  fi
fi

review_delegate_section="$(awk '
  /^## 3-3-septies\./ { capture = 1 }
  capture && /^## 3-3-octies\./ { exit }
  capture { print }
' "$autopilot_wave")"
if [ "$(printf '%s\n' "$review_delegate_section" \
  | grep -Fc "$autopilot_marker_start" || true)" -ne 1 ] \
  || [ "$(printf '%s\n' "$review_delegate_section" \
  | grep -Fc "$autopilot_marker_end" || true)" -ne 1 ]; then
  fail "persona source marker block must stay inside review-delegate handling"
fi

autopilot_persona_source="$(awk -v start="$autopilot_marker_start" \
  -v end="$autopilot_marker_end" '
  $0 == start { capture = 1; next }
  $0 == end { capture = 0; exit }
  capture { print }
' "$autopilot_wave")"
autopilot_source_reference_count="$({
  printf '%s\n' "$autopilot_persona_source" \
    | grep -Fo 'review-persona-contract' || true
} | wc -l | tr -d ' ')"
if [ "$autopilot_source_reference_count" -ne 1 ]; then
  fail "autopilot persona source block must reference review-persona-contract once"
fi

if grep -Eq 'personas/[[:alnum:]_-]+\.md' "$autopilot_wave"; then
  fail "autopilot must not duplicate or extend the canonical persona path list"
fi

require_single_marker_pair \
  "$autopilot_wave" "$zero_file_marker_start" "$zero_file_marker_end" \
  "deterministic zero-file short circuit"
zero_file_block="$(marker_block \
  "$autopilot_wave" "$zero_file_marker_start" "$zero_file_marker_end")"
for expected in \
  '0매치' \
  'adapters/apis/' \
  'models/' \
  'repository' \
  'classify_review_paths.py --null-stdin' \
  '`zero-match`' \
  '`review`' \
  'classifier 실패'; do
  require_block_text "$zero_file_block" "$expected" "zero-file short circuit"
done
if [ "$(printf '%s\n' "$review_delegate_section" \
  | grep -Fc -- "$zero_file_marker_start" || true)" -ne 1 ] \
  || [ "$(printf '%s\n' "$review_delegate_section" \
  | grep -Fc -- "$zero_file_marker_end" || true)" -ne 1 ]; then
  fail "zero-file short circuit must stay inside review-delegate handling"
fi

require_single_marker_pair \
  "$process_skill" "$final_delegate_marker_start" "$final_delegate_marker_end" \
  "process-ticket final review delegation"
final_delegate_block="$(marker_block \
  "$process_skill" "$final_delegate_marker_start" "$final_delegate_marker_end")"
for expected in \
  'final-review-delegate: <이슈 번호>' \
  'worktree: <WORKTREE_ABS 절대경로>' \
  'head: <commit_done과 같은 40자 SHA>' \
  'criteria_digest: <frozen criteria manifest SHA-256>' \
  'base_sha: <frozen merge-base SHA>' \
  'diff_sha256: <exact committed.diff SHA-256>' \
  'owner: <runtime canonical owner identity>' \
  'implementer: <runtime canonical implementer identity>' \
  'final-review-result: <이슈 번호>' \
  'reviewer: <runtime canonical reviewer identity>' \
  'untrusted review data' \
  'merge-base' \
  '"head_sha": "<exact head>"' \
  '"base_sha": "<frozen merge-base SHA>"' \
  '"diff_sha256": "<exact committed.diff SHA-256>"' \
  '"criteria_digest": "<frozen criteria digest>"' \
  'runtime registry에 현재 권한을 보유한 canonical resume member' \
  'self-declared owner' \
  'runtime spawn 결과의 canonical identity' \
  'envelope의 `sender`가 위임을 보낸 canonical `team-lead` identity' \
  '다른 teammate나 reviewer가 직접 보낸 회신' \
  'byte-for-byte 일치'; do
  require_block_text "$final_delegate_block" "$expected" "final review delegation"
done

require_single_marker_pair \
  "$process_phase5" "$rehydrate_marker_start" "$rehydrate_marker_end" \
  "final review resume rehydration"
rehydrate_block="$(marker_block \
  "$process_phase5" "$rehydrate_marker_start" "$rehydrate_marker_end")"
for expected in \
  'review_receipt.py resume-inputs' \
  '.temp_dir' \
  '.manifest_path' \
  '.issue_body_path' \
  '.diff_path' \
  '.head_sha' \
  '.criteria_digest' \
  '.base_sha' \
  '.diff_sha256'; do
  require_block_text "$rehydrate_block" "$expected" "final review resume rehydration"
done

require_single_marker_pair \
  "$autopilot_wave" "$final_handler_marker_start" "$final_handler_marker_end" \
  "autopilot final review handler"
final_handler_block="$(marker_block \
  "$autopilot_wave" "$final_handler_marker_start" "$final_handler_marker_end")"
for expected in \
  'orchestration runtime이 spawn 결과로 반환한 canonical agent identity' \
  'C01–C14 정확히 14개' \
  'disposition=reverified' \
  'result_json' \
  'owner == state.owner == original {PROCESS_OWNER_ID}' \
  'runtime registry에 현재 권한을 보유한 canonical resume member' \
  'self-declared owner' \
  'implementer == state.implementer' \
  'head_sha == delegate.head' \
  'base_sha == delegate.base_sha' \
  'diff_sha256 == delegate.diff_sha256' \
  'criteria_digest == delegate.criteria_digest' \
  'untrusted review data' \
  'review subject' \
  'merge-base' \
  '{command, head_sha, exit_code, output_digest}'; do
  require_block_text "$final_handler_block" "$expected" "autopilot final review handler"
done

require_single_marker_pair \
  "$process_skill" "$identity_producer_marker_start" \
  "$identity_producer_marker_end" "review identity producer"
identity_producer_block="$(marker_block \
  "$process_skill" "$identity_producer_marker_start" \
  "$identity_producer_marker_end")"
for expected in \
  'runtime canonical task/team-member identity' \
  'direct mode' \
  'fail-closed' \
  'immutable identity' \
  'spawn runtime 반환' \
  'reviewer 출력 문자열은 폐기' \
  'commit 전 state' \
  'resume'; do
  require_block_text "$identity_producer_block" "$expected" \
    "review identity producer"
done
for expected in \
  'PROCESS_OWNER_ID binding (필수)' \
  'spawn 반환/envelope' \
  'owner == state.owner == original {PROCESS_OWNER_ID}' \
  'runtime registry에 현재 권한을 보유한 canonical resume member' \
  'resume member는 owner를 사칭하거나 덮어쓰지 않는다'; do
  if ! grep -Fq -- "$expected" "$autopilot_wave"; then
    fail "autopilot owner identity binding must include: $expected"
  fi
done
for expected in \
  'immutable identity' \
  '첫 mutation 후 implementer handoff·state identity 덮어쓰기' \
  'if has("implementer") then' \
  'else error("immutable implementer mismatch")' \
  'else .implementer = $i'; do
  if ! grep -Fq -- "$expected" "$process_phase4"; then
    fail "Phase 4 implementer producer must include: $expected"
  fi
done
if grep -Fq -- "'.implementer = \$i | .updated_at = \$t'" "$process_phase4"; then
  fail "Phase 4 must not overwrite an existing implementer checkpoint"
fi

require_single_marker_pair \
  "$process_skill" "$process_resume_marker_start" "$process_resume_marker_end" \
  "process-ticket publication resume"
process_resume_block="$(marker_block \
  "$process_skill" "$process_resume_marker_start" "$process_resume_marker_end")"
for expected in \
  'stored `publication.state`는 힌트로만' \
  '`pending`·`incomplete`·`published`' \
  '/pr-review <PR_NUMBER> --process-state <WORKTREE_ABS>/.process-state.json' \
  '/update-project-status <ISSUE_NUMBER> In Review' \
  'PR identity → In Review → publication' \
  'publication.state == "published"' \
  'Phase 6 `monitor-pr`/`watch.sh`' \
  'fresh review fallback' \
  '`review_fast_path` enrollment marker 부재' \
  'legacy in-flight state' \
  'resolve_phase5_resume.py' \
  '`git ls-remote --heads`' \
  '`build-full`' \
  'same-repo·same-branch·exact-head OPEN PR' \
  'remote exact HEAD push evidence'; do
  require_block_text "$process_resume_block" "$expected" "process-ticket publication resume"
done

require_single_marker_pair \
  "$autopilot_wave" "$autopilot_resume_marker_start" "$autopilot_resume_marker_end" \
  "autopilot publication resume"
autopilot_resume_block="$(marker_block \
  "$autopilot_wave" "$autopilot_resume_marker_start" "$autopilot_resume_marker_end")"
for expected in \
  'publication state는 힌트로만' \
  '`pending`·`incomplete`·`published`' \
  '/pr-review <PR_NUMBER> --process-state <WORKTREE_ABS>/.process-state.json' \
  '/update-project-status <ISSUE_NUMBER> In Review' \
  'publication.state == "published"' \
  'Phase 6 `monitor-pr`/`watch.sh`' \
  'manual fresh review fallback'; do
  require_block_text "$autopilot_resume_block" "$expected" "autopilot publication resume"
done

require_single_marker_pair \
  "$process_phase5" "$phase5_resume_marker_start" "$phase5_resume_marker_end" \
  "Phase 5 crash-window resume"
phase5_resume_block="$(marker_block \
  "$process_phase5" "$phase5_resume_marker_start" "$phase5_resume_marker_end")"
for expected in \
  'resolve_phase5_resume.py' \
  'caller-supplied remote SHA를 받지 않는다' \
  'final reviewer·`build-full`을 재실행하지 않는다' \
  '`push_done`·`push_head`' \
  'origin exact HEAD' \
  'PR identity → In Review → publication' \
  '`resume-final-review-inputs`' \
  '`resume-cleanup-final-review-inputs`' \
  '`resume-cleanup-blocked-review-inputs`' \
  '`resume-phase4-after-block`' \
  '`cleanup-inputs`' \
  'state key를 원자적으로 먼저 소비' \
  '["live-pr-identity-readback","project-status-in-review","receipt-publisher","live-publication-readback"]' \
  '`review_fast_path` enrollment marker' \
  'fail-closed'; do
  require_block_text "$phase5_resume_block" "$expected" "Phase 5 crash-window resume"
done

require_single_marker_pair \
  "$pr_review_skill" "$manual_mode_marker_start" "$manual_mode_marker_end" \
  "pr-review manual mode"
manual_mode_block="$(marker_block \
  "$pr_review_skill" "$manual_mode_marker_start" "$manual_mode_marker_end")"
for expected in \
  '/pr-review <PR>` (`--process-state` 없음)' \
  'AUTO_APPROVE' \
  'CHANGES_REQUESTED' \
  'HUMAN_REVIEW' \
  '/pr-review <PR> --process-state <PATH>' \
  'resolve_review_mode.py' \
  'mode=manual-fresh' \
  'mode=receipt-publication' \
  '기본 fresh review로 fallback하지 않는다'; do
  require_block_text "$manual_mode_block" "$expected" "pr-review manual mode"
done

phase5_identity_line="$(grep -nF -- '**PR identity read-back + 체크포인트 갱신**' \
  "$process_phase5" | cut -d: -f1 || true)"
phase5_in_review_line="$(grep -nF -- '**이슈/프로젝트 상태 갱신' \
  "$process_phase5" | cut -d: -f1 || true)"
phase5_publish_line="$(grep -nF -- '**receipt publication fast path**' \
  "$process_phase5" | cut -d: -f1 || true)"
if [ -z "$phase5_identity_line" ] || [ -z "$phase5_in_review_line" ] \
  || [ -z "$phase5_publish_line" ]; then
  fail "Phase 5 must declare PR identity, In Review, and publication steps"
elif [ "$phase5_identity_line" -ge "$phase5_in_review_line" ] \
  || [ "$phase5_in_review_line" -ge "$phase5_publish_line" ]; then
  fail "Phase 5 ordering must be PR identity -> In Review -> publication"
fi

for expected in \
  '7. **PR identity read-back + 체크포인트 갱신**' \
  '8. **이슈/프로젝트 상태 갱신' \
  '9. **receipt publication fast path**' \
  '6. **existing exact PR adopt → create → metadata convergence**' \
  '/create-pr {ISSUE-NUMBER} --metadata-only {PR_NUMBER}' \
  "owner=\$(jq -er '.owner | strings | select(length > 0)'" \
  "implementer=\$(jq -er '.implementer | strings | select(length > 0)'" \
  '.commit_done = $h | .updated_at = $t' \
  '.final_review_inputs = {temp_dir: $d, manifest_path: $m, issue_body_path: $b, diff_path: $f, head_sha: $h, criteria_digest: $c, base_sha: $s, diff_sha256: $x}' \
  '.final_review_delegate = {head_sha: $h, criteria_digest: $c, reviewer: $r}' \
  'review_receipt.py cleanup-inputs' \
  'review_receipt.py resume-inputs' \
  'test "$base_sha" = "$(jq -r '\''.base_sha'\''' \
  'test "$diff_sha256" = "$(jq -r '\''.diff_sha256'\''' \
  'untrusted review data' \
  'merge-base' \
  'process state의 canonical `owner`·`implementer`·`final_review_delegate`'; do
  if ! grep -Fq -- "$expected" "$process_phase5"; then
    fail "Phase 5 final review provenance must include: $expected"
  fi
done
if grep -Fq -- '.owner = $o | .implementer = $i' "$process_phase5"; then
  fail "Phase 5 must not overwrite authoritative owner/implementer identities"
fi
if grep -Eq -- '--(owner|implementer|reviewer)([=[:space:]]|$)' "$process_phase5"; then
  fail "Phase 5 build-full must not accept identity flags"
fi
if grep -Eq -- "trap[[:space:]]+.*tmp_dir|trap[[:space:]]+.*spakky-final-review" \
  "$process_phase5"; then
  fail "Phase 5 must not register early cleanup for delegated final-review inputs"
fi

phase5_input_state_line="$(grep -nF -- '.final_review_inputs = {temp_dir: $d' \
  "$process_phase5" | cut -d: -f1 || true)"
phase5_delegate_line="$(grep -nF -- 'teammate mode는 `final-review-delegate`에' \
  "$process_phase5" | cut -d: -f1 || true)"
phase5_rehydrate_line="$(grep -nF -- '<!-- final-review-resume-rehydrate:start -->' \
  "$process_phase5" | cut -d: -f1 || true)"
phase5_build_line="$(grep -nF -- 'review_receipt.py build-full' \
  "$process_phase5" | cut -d: -f1 || true)"
phase5_cleanup_line="$(grep -nF -- 'cleanup_result=$(uv run python .agents/skills/process-ticket/scripts/review_receipt.py cleanup-inputs' \
  "$process_phase5" | cut -d: -f1 || true)"
if [ -z "$phase5_input_state_line" ] || [ -z "$phase5_delegate_line" ] \
  || [ -z "$phase5_rehydrate_line" ] || [ -z "$phase5_build_line" ] \
  || [ -z "$phase5_cleanup_line" ]; then
  fail "Phase 5 must persist handoff inputs and explicitly clean them after build"
elif [ "$phase5_input_state_line" -ge "$phase5_delegate_line" ] \
  || [ "$phase5_delegate_line" -ge "$phase5_rehydrate_line" ] \
  || [ "$phase5_rehydrate_line" -ge "$phase5_build_line" ] \
  || [ "$phase5_build_line" -ge "$phase5_cleanup_line" ]; then
  fail "Phase 5 input lifecycle must be persist -> delegate -> build -> cleanup"
fi
cleanup_state_line="$(grep -nF -- 'state.pop("final_review_inputs")' \
  "$review_receipt_script" | cut -d: -f1 || true)"
cleanup_unlink_line="$(grep -nF -- 'path.unlink()' \
  "$review_receipt_script" | cut -d: -f1 || true)"
if [ -z "$cleanup_state_line" ] || [ -z "$cleanup_unlink_line" ]; then
  fail "cleanup-inputs must consume state and explicitly unlink canonical files"
elif [ "$cleanup_state_line" -ge "$cleanup_unlink_line" ]; then
  fail "cleanup-inputs must atomically consume state before temporary file deletion"
fi
for expected in \
  'def cleanup_final_review_inputs(' \
  'validate_final_review_inputs(state, root, policy_path)' \
  'durable receipt differs from the final review result' \
  'directory.rmdir()'; do
  if ! grep -Fq -- "$expected" "$review_receipt_script"; then
    fail "cleanup-inputs executable contract must include: $expected"
  fi
done

for expected in \
  'jq -n --argjson n "$ISSUE_NUMBER"' \
  '--arg o "$PROCESS_OWNER_ID"' \
  'owner: $o' \
  'review_fast_path: {schema_version: 1, mode: "exact-head-receipt"}' \
  'mv "$WORKTREE_ABS/.process-state.json.tmp" "$WORKTREE_ABS/.process-state.json"'; do
  if ! grep -Fq -- "$expected" "$process_phase3"; then
    fail "Phase 3 process state must preserve numeric issue_number: $expected"
  fi
done
if grep -Fq -- '"issue_number": "{ISSUE-NUMBER}"' "$process_phase3"; then
  fail "Phase 3 process state must not serialize issue_number as a string"
fi

if [ "$failures" -ne 0 ]; then
  printf 'review-delegate context contract failed: %s violation(s)\n' "$failures" >&2
  exit 1
fi

echo "review-delegate context contract checks passed"
