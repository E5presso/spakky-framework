#!/usr/bin/env bash
# Verify the sync-docs delivery pointer and prove its contract is mutation-sensitive.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/sync-docs-delivery-contract.XXXXXX")"

cleanup() {
  rm -rf -- "$fixture_root"
}
trap cleanup EXIT

validate_contract() {
  local root="$1"
  local phase="$root/.agents/skills/autopilot/phases/phase-5-sync-docs.md"
  local pointer
  local pointer_count
  local contract
  local contract_block
  local failures=0

  pointer="$(grep -oE 'sync-docs/[^` )]+\.md' "$phase" | head -1 || true)"
  pointer_count="$({ grep -oE 'sync-docs/[^` )]+\.md' "$phase" || true; } \
    | sort -u | sed '/^$/d' | wc -l | tr -d ' ')"
  if [ "$pointer_count" -ne 1 ] || [ -z "$pointer" ]; then
    printf 'sync-docs delivery contract: Phase 5 must reference one Markdown SSOT\n' >&2
    failures=$((failures + 1))
  fi

  if ! grep -Fq 'pr: <URL> (미머지 — <사유>)' "$phase"; then
    printf 'sync-docs delivery contract: Phase 5 must preserve the unmerged result syntax\n' >&2
    failures=$((failures + 1))
  fi

  contract="$root/.agents/skills/$pointer"
  if [ -z "$pointer" ] || [ ! -f "$contract" ]; then
    printf 'sync-docs delivery contract: missing pointer target: %s\n' "$pointer" >&2
    return 1
  fi

  if [ "$(grep -Fc '<!-- sync-docs-delivery-contract:start -->' "$contract" || true)" -ne 1 ] \
    || [ "$(grep -Fc '<!-- sync-docs-delivery-contract:end -->' "$contract" || true)" -ne 1 ]; then
    printf 'sync-docs delivery contract: expected one canonical marker block\n' >&2
    return 1
  fi

  contract_block="$(awk '
    $0 == "<!-- sync-docs-delivery-contract:start -->" { capture = 1; next }
    $0 == "<!-- sync-docs-delivery-contract:end -->" { capture = 0; exit }
    capture { print }
  ' "$contract")"

  for required_line in \
    '- delivery-workspace: dedicated-worktree' \
    '- delivery-commit: required-when-updated' \
    '- delivery-push: verified-remote-head' \
    '- delivery-pr: required-when-updated' \
    '- delivery-merge: gated-squash' \
    '- result-updated: `updated: <N>개`' \
    '- result-pr-merged: `pr: <URL>`' \
    '- result-pr-none: `pr: none`' \
    '- result-pr-unmerged: `pr: <URL> (미머지 — <사유>)`'; do
    if ! printf '%s\n' "$contract_block" | grep -Fq -- "$required_line"; then
      printf 'sync-docs delivery contract: missing responsibility: %s\n' "$required_line" >&2
      failures=$((failures + 1))
    fi
  done

  [ "$failures" -eq 0 ]
}

make_fixture() {
  local name="$1"
  local root="$fixture_root/$name"

  mkdir -p \
    "$root/.agents/skills/autopilot/phases" \
    "$root/.agents/skills/sync-docs"
  cp "$repo_root/.agents/skills/autopilot/phases/phase-5-sync-docs.md" \
    "$root/.agents/skills/autopilot/phases/"
  cp "$repo_root/.agents/skills/sync-docs/SKILL.md" \
    "$root/.agents/skills/sync-docs/"
  printf '%s\n' "$root"
}

validate_contract "$repo_root"

missing_pointer_fixture="$(make_fixture missing-pointer)"
sed -i.bak 's#sync-docs/SKILL\.md#sync-docs/missing.md#g' \
  "$missing_pointer_fixture/.agents/skills/autopilot/phases/phase-5-sync-docs.md"
rm "$missing_pointer_fixture/.agents/skills/autopilot/phases/phase-5-sync-docs.md.bak"
if validate_contract "$missing_pointer_fixture" >/dev/null 2>&1; then
  echo 'nonexistent pointer mutation unexpectedly passed' >&2
  exit 1
fi

missing_delivery_fixture="$(make_fixture missing-delivery)"
sed -i.bak '/^- delivery-workspace: dedicated-worktree/d' \
  "$missing_delivery_fixture/.agents/skills/sync-docs/SKILL.md"
rm "$missing_delivery_fixture/.agents/skills/sync-docs/SKILL.md.bak"
if validate_contract "$missing_delivery_fixture" >/dev/null 2>&1; then
  echo 'delivery responsibility mutation unexpectedly passed' >&2
  exit 1
fi

missing_result_fixture="$(make_fixture missing-result)"
sed -i.bak '/^- result-pr-/d' \
  "$missing_result_fixture/.agents/skills/sync-docs/SKILL.md"
rm "$missing_result_fixture/.agents/skills/sync-docs/SKILL.md.bak"
if validate_contract "$missing_result_fixture" >/dev/null 2>&1; then
  echo 'pr result mutation unexpectedly passed' >&2
  exit 1
fi

missing_unmerged_fixture="$(make_fixture missing-unmerged-result)"
sed -i.bak '/^- result-pr-unmerged:/d' \
  "$missing_unmerged_fixture/.agents/skills/sync-docs/SKILL.md"
rm "$missing_unmerged_fixture/.agents/skills/sync-docs/SKILL.md.bak"
if validate_contract "$missing_unmerged_fixture" >/dev/null 2>&1; then
  echo 'unmerged pr result mutation unexpectedly passed' >&2
  exit 1
fi

echo 'sync-docs delivery contract checks passed'
