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
  "$fixture_root/.agents/skills"
cp -R "$repo_root/.agents/rules" "$fixture_root/.agents/"
cp -R "$repo_root/.agents/skills/review-code" "$fixture_root/.agents/skills/"
cp "$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md" \
  "$fixture_root/.agents/skills/autopilot/phases/"
cp "$repo_root/.agents/skills/autopilot/scripts/check_review_delegate_context_contract.sh" \
  "$fixture_root/.agents/skills/autopilot/scripts/"

fixture_check="$fixture_root/.agents/skills/autopilot/scripts/check_review_delegate_context_contract.sh"
"$fixture_check" >/dev/null

autopilot_wave="$fixture_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md"
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
