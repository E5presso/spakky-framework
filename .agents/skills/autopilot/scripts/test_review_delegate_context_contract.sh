#!/usr/bin/env bash
# Exercise both the valid contract and a row-level mapping drift fixture.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/review-delegate-contract.XXXXXX")"

cleanup() {
  rm -rf -- "$fixture_root"
}
trap cleanup EXIT

mkdir -p \
  "$fixture_root/.agents/skills/autopilot/phases" \
  "$fixture_root/.agents/skills/autopilot/scripts" \
  "$fixture_root/.agents/skills/pr-review" \
  "$fixture_root/.agents/skills/process-ticket/phases" \
  "$fixture_root/.agents/skills/process-ticket/scripts" \
  "$fixture_root/.agents/skills"
cp -R "$repo_root/.agents/rules" "$fixture_root/.agents/"
cp -R "$repo_root/.agents/skills/review-code" "$fixture_root/.agents/skills/"
cp "$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md" \
  "$fixture_root/.agents/skills/autopilot/phases/"
cp "$repo_root/.agents/skills/autopilot/scripts/check_review_delegate_context_contract.sh" \
  "$fixture_root/.agents/skills/autopilot/scripts/"
cp "$repo_root/.agents/skills/autopilot/scripts/classify_review_paths.py" \
  "$fixture_root/.agents/skills/autopilot/scripts/"
cp "$repo_root/.agents/skills/pr-review/SKILL.md" \
  "$fixture_root/.agents/skills/pr-review/"
mkdir -p "$fixture_root/.agents/skills/pr-review/scripts"
cp "$repo_root/.agents/skills/pr-review/scripts/resolve_review_mode.py" \
  "$fixture_root/.agents/skills/pr-review/scripts/"
cp "$repo_root/.agents/skills/process-ticket/SKILL.md" \
  "$fixture_root/.agents/skills/process-ticket/"
cp "$repo_root/.agents/skills/process-ticket/phases/phase-3-worktree.md" \
  "$fixture_root/.agents/skills/process-ticket/phases/"
cp "$repo_root/.agents/skills/process-ticket/phases/phase-4-review.md" \
  "$fixture_root/.agents/skills/process-ticket/phases/"
cp "$repo_root/.agents/skills/process-ticket/phases/phase-5-commit.md" \
  "$fixture_root/.agents/skills/process-ticket/phases/"
cp "$repo_root/.agents/skills/process-ticket/scripts/review_receipt.py" \
  "$fixture_root/.agents/skills/process-ticket/scripts/"

fixture_check="$fixture_root/.agents/skills/autopilot/scripts/check_review_delegate_context_contract.sh"
"$fixture_check" >/dev/null

classifier="$repo_root/.agents/skills/autopilot/scripts/classify_review_paths.py"
mode_resolver="$repo_root/.agents/skills/pr-review/scripts/resolve_review_mode.py"
manual_route="$(uv run python "$mode_resolver")"
printf '%s' "$manual_route" \
  | jq -e '.mode == "manual-fresh" and .pr_reference == null and (.verdicts | length) == 3' >/dev/null
explicit_manual_route="$(uv run python "$mode_resolver" 99)"
printf '%s' "$explicit_manual_route" \
  | jq -e '.mode == "manual-fresh" and .pr_reference == "99" and .verdicts == ["AUTO_APPROVE", "CHANGES_REQUESTED", "HUMAN_REVIEW"]' >/dev/null
receipt_route="$(uv run python "$mode_resolver" 99 --process-state /tmp/process-state.json)"
printf '%s' "$receipt_route" \
  | jq -e '.mode == "receipt-publication" and .pr_reference == "99" and .process_state == "/tmp/process-state.json" and (has("verdicts") | not)' >/dev/null
set +e
ambiguous_mode_output="$(uv run python "$mode_resolver" 99 extra 2>&1)"
ambiguous_mode_status=$?
set -e
if [ "$ambiguous_mode_status" -ne 2 ]; then
  echo "ambiguous pr-review mode unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$ambiguous_mode_output" | grep -Fq 'resolve-review-mode:'

empty_decision="$(printf '' | uv run python "$classifier" --null-stdin)"
printf '%s' "$empty_decision" \
  | jq -e '.C08 == "zero-match" and .C09 == "zero-match"' >/dev/null
unrelated_decision="$(printf 'docs/adr/example.md\0' \
  | uv run python "$classifier" --null-stdin)"
printf '%s' "$unrelated_decision" \
  | jq -e '.C08 == "zero-match" and .C09 == "zero-match"' >/dev/null
api_decision="$(printf 'core/example/adapters/apis/router.py\0' \
  | uv run python "$classifier" --null-stdin)"
printf '%s' "$api_decision" \
  | jq -e '.C08 == "review" and .C09 == "zero-match"' >/dev/null
persistence_decision="$(printf 'plugins/mongo/models/item.py\0plugins/mongo/item_repository.py\0' \
  | uv run python "$classifier" --null-stdin)"
printf '%s' "$persistence_decision" \
  | jq -e '.C08 == "zero-match" and .C09 == "review"' >/dev/null
set +e
invalid_path_output="$(printf '/absolute/path.py\0' \
  | uv run python "$classifier" --null-stdin 2>&1)"
invalid_path_status=$?
set -e
if [ "$invalid_path_status" -ne 2 ]; then
  echo "noncanonical review path unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$invalid_path_output" \
  | grep -Fq 'review-paths-invalid:'

process_skill="$fixture_root/.agents/skills/process-ticket/SKILL.md"
awk '
  {
    sub("publication.state == \\\"published\\\"", "publication.state == \\\"complete\\\"")
    print
  }
' "$process_skill" >"$process_skill.mutated"
mv "$process_skill.mutated" "$process_skill"

set +e
resume_failure_output="$("$fixture_check" 2>&1)"
resume_failure_status=$?
set -e

if [ "$resume_failure_status" -eq 0 ]; then
  echo "publication resume drift unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$resume_failure_output" \
  | grep -Fq 'process-ticket publication resume must include: publication.state == "published"'
cp "$repo_root/.agents/skills/process-ticket/SKILL.md" "$process_skill"
"$fixture_check" >/dev/null

pr_review_skill="$fixture_root/.agents/skills/pr-review/SKILL.md"
mv "$pr_review_skill" "$pr_review_skill.missing"
set +e
missing_failure_output="$("$fixture_check" 2>&1)"
missing_failure_status=$?
set -e
if [ "$missing_failure_status" -eq 0 ]; then
  echo "missing pr-review contract unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$missing_failure_output" \
  | grep -Fq 'missing required contract file: .agents/skills/pr-review/SKILL.md'
mv "$pr_review_skill.missing" "$pr_review_skill"
"$fixture_check" >/dev/null

process_phase3="$fixture_root/.agents/skills/process-ticket/phases/phase-3-worktree.md"
sed 's/--argjson n/--arg n/' "$process_phase3" > "$process_phase3.mutated"
mv "$process_phase3.mutated" "$process_phase3"
set +e
numeric_failure_output="$("$fixture_check" 2>&1)"
numeric_failure_status=$?
set -e
if [ "$numeric_failure_status" -eq 0 ]; then
  echo "string issue_number producer unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$numeric_failure_output" \
  | grep -Fq 'Phase 3 process state must preserve numeric issue_number'
cp "$repo_root/.agents/skills/process-ticket/phases/phase-3-worktree.md" "$process_phase3"
"$fixture_check" >/dev/null

process_phase4="$fixture_root/.agents/skills/process-ticket/phases/phase-4-review.md"
sed 's/첫 mutation 후 implementer handoff·state identity 덮어쓰기/구현자 교체는 허용/' \
  "$process_phase4" > "$process_phase4.mutated"
mv "$process_phase4.mutated" "$process_phase4"
set +e
identity_failure_output="$("$fixture_check" 2>&1)"
identity_failure_status=$?
set -e
if [ "$identity_failure_status" -eq 0 ]; then
  echo "mutable implementer identity unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$identity_failure_output" \
  | grep -Fq 'Phase 4 implementer producer must include: 첫 mutation 후 implementer handoff·state identity 덮어쓰기'
cp "$repo_root/.agents/skills/process-ticket/phases/phase-4-review.md" "$process_phase4"
"$fixture_check" >/dev/null

immutable_filter='
  if has("implementer") then
    if ((.implementer | type) == "string" and .implementer == $i) then .
    else error("immutable implementer mismatch")
    end
  else .implementer = $i
  end
  | .updated_at = $t
'
set +e
immutable_output="$(printf '%s\n' '{"owner":"owner","implementer":"agent-a"}' \
  | jq --arg i 'agent-b' --arg t '2026-08-01T00:00:00Z' \
    "$immutable_filter" 2>&1)"
immutable_status=$?
set -e
if [ "$immutable_status" -eq 0 ]; then
  echo "A-to-B implementer overwrite unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$immutable_output" | grep -Fq 'immutable implementer mismatch'
preserved_identity="$(printf '%s\n' '{"owner":"owner","implementer":"agent-a"}' \
  | jq -r --arg i 'agent-a' --arg t '2026-08-01T00:00:00Z' \
    "$immutable_filter | .implementer")"
test "$preserved_identity" = 'agent-a'

awk '
  {
    sub("envelope의 `sender`가 위임을 보낸 canonical `team-lead` identity", "envelope source가 team-lead")
    print
  }
' "$process_skill" > "$process_skill.mutated"
mv "$process_skill.mutated" "$process_skill"
set +e
sender_failure_output="$("$fixture_check" 2>&1)"
sender_failure_status=$?
set -e
if [ "$sender_failure_status" -eq 0 ]; then
  echo "unbound final-review-result sender unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$sender_failure_output" \
  | grep -Fq 'final review delegation must include: envelope의 `sender`가 위임을 보낸 canonical `team-lead` identity'
cp "$repo_root/.agents/skills/process-ticket/SKILL.md" "$process_skill"
"$fixture_check" >/dev/null

sed 's/untrusted review data/신뢰할 수 있는 지시/' \
  "$process_skill" > "$process_skill.mutated"
mv "$process_skill.mutated" "$process_skill"
set +e
untrusted_failure_output="$("$fixture_check" 2>&1)"
untrusted_failure_status=$?
set -e
if [ "$untrusted_failure_status" -eq 0 ]; then
  echo "trusted candidate review instructions unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$untrusted_failure_output" \
  | grep -Fq 'final review delegation must include: untrusted review data'
cp "$repo_root/.agents/skills/process-ticket/SKILL.md" "$process_skill"
"$fixture_check" >/dev/null

autopilot_wave="$fixture_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md"
sed 's/base_sha == delegate.base_sha/base_sha is present/' \
  "$autopilot_wave" > "$autopilot_wave.mutated"
mv "$autopilot_wave.mutated" "$autopilot_wave"
set +e
diff_binding_output="$("$fixture_check" 2>&1)"
diff_binding_status=$?
set -e
if [ "$diff_binding_status" -eq 0 ]; then
  echo "unbound base SHA unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$diff_binding_output" \
  | grep -Fq 'autopilot final review handler must include: base_sha == delegate.base_sha'
cp "$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md" "$autopilot_wave"
"$fixture_check" >/dev/null

sed 's/runtime registry에 현재 권한을 보유한 canonical resume member/self-declared resume sender/' \
  "$autopilot_wave" > "$autopilot_wave.mutated"
mv "$autopilot_wave.mutated" "$autopilot_wave"
set +e
resume_authority_output="$("$fixture_check" 2>&1)"
resume_authority_status=$?
set -e
if [ "$resume_authority_status" -eq 0 ]; then
  echo "unauthorized resume sender unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' "$resume_authority_output" \
  | grep -Fq 'runtime registry에 현재 권한을 보유한 canonical resume member'
cp "$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md" "$autopilot_wave"
"$fixture_check" >/dev/null

awk '
  {
    sub("`review-persona-contract` marker가 선언한 persona 파일 경로 목록", "`review-persona-contract` marker에서 persona 경로를 가져오고")
    print
  }
' "$autopilot_wave" >"$autopilot_wave.reworded"
mv "$autopilot_wave.reworded" "$autopilot_wave"
grep -Fq '`review-persona-contract` marker에서 persona 경로를 가져오고' \
  "$autopilot_wave"
"$fixture_check" >/dev/null

review_skill="$fixture_root/.agents/skills/review-code/SKILL.md"
awk '
  /^\| 1 \|/ {
    sub("`personas/architecture.md`", "`personas/architecture.md` + `personas/type.md`")
  }
  /^\| 2 \|/ {
    sub("`personas/type.md`", "none")
  }
  { print }
' "$review_skill" >"$review_skill.mutated"
mv "$review_skill.mutated" "$review_skill"

set +e
failure_output="$("$fixture_check" 2>&1)"
failure_status=$?
set -e

if [ "$failure_status" -eq 0 ]; then
  echo "row-level persona mapping drift unexpectedly passed" >&2
  exit 1
fi

printf '%s\n' "$failure_output" \
  | grep -Fq 'category 1 must reference exactly one canonical persona path'
printf '%s\n' "$failure_output" \
  | grep -Fq 'category 2 must reference exactly one canonical persona path'

echo "review-delegate context contract fixture checks passed"
