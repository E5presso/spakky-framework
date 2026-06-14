#!/usr/bin/env bash
# Formats and type-checks edited package Python files from the package root.

set -u

input="$(cat)"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -z "$repo_root" ] && exit 0
repo_root="$(cd "$repo_root" 2>/dev/null && pwd -P || printf '%s\n' "$repo_root")"

tool_input_text() {
  local preferred_key="$1"
  printf '%s' "$input" \
    | jq -r --arg preferred_key "$preferred_key" '
        .tool_input as $tool_input
        | if ($tool_input | type) == "string" then
            $tool_input
          elif ($tool_input | type) == "object" then
            ($tool_input[$preferred_key] // $tool_input.command // $tool_input.cmd // $tool_input.input // empty)
          else
            empty
          end
      '
}

extract_paths() {
  local tool_name
  tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty')"

  case "$tool_name" in
    Edit|Write|MultiEdit|NotebookEdit)
      printf '%s\n' "$input" \
        | jq -r '
            [
              .tool_response.filePath?,
              .tool_input.file_path?,
              .tool_input.notebook_path?
            ]
            | map(select(type == "string" and length > 0))
            | .[]
          '
      ;;
    apply_patch)
      tool_input_text "command" \
        | awk '
            function flush_pending() {
              if (pending != "") {
                print pending
                pending = ""
              }
            }
            /^\*\*\* Update File: / {
              flush_pending()
              pending = $0
              sub(/^\*\*\* Update File: /, "", pending)
              next
            }
            /^\*\*\* Add File: / {
              flush_pending()
              path = $0
              sub(/^\*\*\* Add File: /, "", path)
              print path
              next
            }
            /^\*\*\* Delete File: / {
              next
            }
            /^\*\*\* Move to: / {
              path = $0
              sub(/^\*\*\* Move to: /, "", path)
              print path
              pending = ""
              next
            }
            END {
              flush_pending()
            }
          '
      ;;
  esac
}

canonicalize_path() {
  local p="$1"
  local probe="$p"
  local tail=""

  if [ -d "${p%/*}" ]; then
    printf '%s/%s\n' "$(cd "${p%/*}" && pwd -P)" "${p##*/}"
    return
  fi

  while [ ! -e "$probe" ] && [ "$probe" != "/" ]; do
    tail="/${probe##*/}${tail}"
    probe="${probe%/*}"
    [ -z "$probe" ] && probe="/"
  done

  if [ -d "$probe" ]; then
    printf '%s%s\n' "$(cd "$probe" && pwd -P)" "$tail"
    return
  fi

  printf '%s\n' "$p"
}

resolve_path() {
  local p="$1"
  case "$p" in
    /*) canonicalize_path "$p" ;;
    *)
      local base
      base="$(printf '%s' "$input" | jq -r '.cwd // .tool_input.workdir // empty')"
      [ -z "$base" ] && base="$(pwd)"
      base="$(cd "$base" 2>/dev/null && pwd -P || printf '%s\n' "$base")"
      canonicalize_path "${base%/}/${p#./}"
      ;;
  esac
}

package_root_for_path() {
  local p="$1"
  local target_repo_root="$2"
  case "$p" in
    "$target_repo_root"/core/*/*.py|"$target_repo_root"/plugins/*/*.py) ;;
    "$target_repo_root"/core/*/*/*.py|"$target_repo_root"/plugins/*/*/*.py) ;;
    *) return ;;
  esac

  local rel rest name pkg_root
  rel="${p#"$target_repo_root"/}"
  case "$rel" in
    core/*)
      rest="${rel#core/}"
      name="${rest%%/*}"
      pkg_root="$target_repo_root/core/$name"
      ;;
    plugins/*)
      rest="${rel#plugins/}"
      name="${rest%%/*}"
      pkg_root="$target_repo_root/plugins/$name"
      ;;
    *) return ;;
  esac

  [ -f "$pkg_root/pyproject.toml" ] && printf '%s\n' "$pkg_root"
}

repo_root_for_path() {
  local p="$1"
  local dir="${p%/*}"

  while [ ! -d "$dir" ] && [ "$dir" != "/" ]; do
    dir="${dir%/*}"
    [ -z "$dir" ] && dir="/"
  done

  git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true
}

errors=""
seen=""
while IFS= read -r raw_path; do
  [ -z "$raw_path" ] && continue
  case "$raw_path" in
    ../*|*/../*|*/..) continue ;;
  esac
  abs_path="$(resolve_path "$raw_path")"
  case "$abs_path" in
    *.py) ;;
    *) continue ;;
  esac
  case "$seen" in
    *"
$abs_path
"*) continue ;;
  esac
  seen="$seen
$abs_path
"

  target_repo_root="$(repo_root_for_path "$abs_path")"
  [ -z "$target_repo_root" ] && continue
  target_repo_root="$(cd "$target_repo_root" 2>/dev/null && pwd -P || printf '%s\n' "$target_repo_root")"

  pkg_root="$(package_root_for_path "$abs_path" "$target_repo_root")"
  [ -z "$pkg_root" ] && continue

  fmt_output="$(cd "$pkg_root" && uv run ruff format "$abs_path" && uv run ruff check --fix "$abs_path" 2>&1)"
  fmt_status=$?
  if [ "$fmt_status" -ne 0 ]; then
    errors="${errors}ruff errors in ${abs_path}:
${fmt_output}
"
    continue
  fi

  type_output="$(cd "$pkg_root" && uv run pyrefly check --min-severity warn --no-progress-bar --output-format min-text "$abs_path" 2>&1)"
  type_status=$?
  if [ "$type_status" -ne 0 ] || printf '%s\n' "$type_output" | grep -Eq '^[[:space:]]+WARN '; then
    errors="${errors}pyrefly errors in ${abs_path}:
${type_output}
"
  fi
done < <(extract_paths)

[ -z "$errors" ] && exit 0

jq -n --arg errors "$errors" \
  '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$errors}}'
exit 1
