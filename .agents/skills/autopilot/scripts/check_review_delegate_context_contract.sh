#!/usr/bin/env bash
# Keep review delegation bound to the canonical review-code context assets.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
review_skill="$repo_root/.agents/skills/review-code/SKILL.md"
review_persona_root="$repo_root/.agents/skills/review-code"
autopilot_wave="$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md"
autopilot_marker_start='<!-- review-delegate-persona-source:start -->'
autopilot_marker_end='<!-- review-delegate-persona-source:end -->'

failures=0

fail() {
  printf 'review-delegate context contract: %s\n' "$1" >&2
  failures=$((failures + 1))
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

if [ "$failures" -ne 0 ]; then
  printf 'review-delegate context contract failed: %s violation(s)\n' "$failures" >&2
  exit 1
fi

echo "review-delegate context contract checks passed"
