#!/usr/bin/env bash
# Regression guard for S1/S7 auto-merge continuation. The harness is markdown
# driven, so this check fails when the clean/green monitor terminal path loses
# either stuck detection or the Phase 8 continuation requirement.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
autopilot_wave="$repo_root/.agents/skills/autopilot/phases/phase-3-wave-loop.md"
phase6="$repo_root/.agents/skills/process-ticket/phases/phase-6-monitor.md"
phase7="$repo_root/.agents/skills/process-ticket/phases/phase-7-merge-gate.md"

failures=0

require_text() {
  local file="$1"
  local needle="$2"
  local label="$3"

  if ! grep -Fq "$needle" "$file"; then
    printf 'missing: %s (%s)\n' "$label" "$file" >&2
    failures=$((failures + 1))
  fi
}

require_text "$autopilot_wave" '모순 C (auto-merge clean terminal 미흡수)' \
  'autopilot stuck detector must classify clean/green monitor_started as stuck'
require_text "$autopilot_wave" 'state.monitor_started' \
  'clean terminal stuck detection must start from monitor_started state'
require_text "$autopilot_wave" 'mergeStateStatus in {"CLEAN","UNSTABLE"}' \
  'clean terminal stuck detection must include CLEAN/UNSTABLE merge states'
require_text "$autopilot_wave" 'pendingChecks == 0' \
  'clean terminal stuck detection must require no pending checks'
require_text "$autopilot_wave" 'failedChecks == 0' \
  'clean terminal stuck detection must require no failed checks'
require_text "$autopilot_wave" 'phase7_ready={phase7_ready|null}' \
  'resume prompt must preserve phase7_ready as a resume input'
require_text "$autopilot_wave" '반환하지 말고 같은 turn에서 `gh pr merge --squash --delete-branch`와 cleanup까지 완료하라' \
  'resume prompt must forbid returning after phase7_ready'

require_text "$phase6" '`DONE reason=mergeable-clean`은 Phase 6만의 terminal이므로' \
  'process-ticket Phase 6 must treat mergeable-clean as nonterminal for auto-merge'
require_text "$phase6" 'Phase 8 squash merge + cleanup까지 계속한다' \
  'process-ticket Phase 6 must continue to Phase 8 in auto-merge mode'
require_text "$phase7" 'Phase 7은 사용자 승인 게이트가 아니라 Phase 8로 넘어가는 0-hop 라우터다' \
  'process-ticket Phase 7 must be a zero-hop router in auto-merge mode'

if [ "$failures" -ne 0 ]; then
  printf 'auto-merge continuation contract failed: %s violation(s)\n' "$failures" >&2
  exit 1
fi

echo "auto-merge continuation contract checks passed"
