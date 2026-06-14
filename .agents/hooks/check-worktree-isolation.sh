#!/usr/bin/env bash
# Blocks file-tool mutations that target the root checkout while worktrees exist.

set -u

input="$(cat)"

git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
[ -z "$git_common_dir" ] && exit 0
repo_root="${git_common_dir%/.git}"
[ -z "$repo_root" ] && exit 0

worktrees_dir="$repo_root/.claude/worktrees"
active_worktrees=0
if [ -d "$worktrees_dir" ]; then
  for entry in "$worktrees_dir"/*; do
    [ -d "$entry" ] && active_worktrees=$((active_worktrees + 1))
  done
fi
[ "$active_worktrees" -eq 0 ] && exit 0

tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty')"

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

resolve_tool_path() {
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

path_inside_any_worktree() {
  case "$1" in
    "$worktrees_dir"/*) return 0 ;;
  esac
  return 1
}

path_targets_root() {
  case "$1" in
    "$repo_root"|"$repo_root"/*) return 0 ;;
  esac
  return 1
}

deny_path() {
  local path="$1"
  jq -n --arg path "$path" --arg repo "$repo_root" --arg wts "$worktrees_dir" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:("Worktree isolation violation: path \($path) targets root checkout \($repo) while active worktrees exist under \($wts). Use the target worktree absolute path.")}}' >&2
  exit 2
}

command_text() {
  tool_input_text "command"
}

command_workdir() {
  printf '%s' "$input" | jq -r '.tool_input.workdir // .cwd // empty'
}

check_mutation_path() {
  case "$1" in
    ../*|*/../*|*/..) deny_path "$1" ;;
  esac

  local path
  path="$(resolve_tool_path "$1")"
  [ -z "$path" ] && return
  path_inside_any_worktree "$path" && return
  path_targets_root "$path" && deny_path "$path"
}

check_shell_command() {
  local cmd="$1" workdir="$2"
  [ -z "$cmd" ] && return

  case "$cmd" in
    *"$repo_root"/../*|*"$repo_root"/..|*"$worktrees_dir"/*/../*) deny_path "$cmd" ;;
  esac

  case "$cmd" in
    *"$repo_root"/*|*"$repo_root")
      case "$cmd" in
        *"$worktrees_dir"/*) ;;
        *"touch "*|*"rm "*|*"mv "*|*"cp "*|*"mkdir "*|*"rmdir "*|*"tee "*|*">"*|*">>"*) deny_path "$cmd" ;;
      esac
      ;;
  esac

  [ -z "$workdir" ] && return
  local resolved_workdir
  resolved_workdir="$(resolve_tool_path "$workdir")"
  path_inside_any_worktree "$resolved_workdir" && return
  path_targets_root "$resolved_workdir" || return

  case "$cmd" in
    *"cd $worktrees_dir/"*|*"cd \"$worktrees_dir/"*)
      case "$cmd" in
        *"cd -"*|*"builtin cd -"*|*"eval "*"cd -"*) deny_path "$cmd" ;;
        *) return ;;
      esac
      ;;
    *"git -C $worktrees_dir/"*|*"git -C \"$worktrees_dir/"*)
      case "$cmd" in
        *"; touch "*|*"&& touch "*|*"|| touch "*|*"; mkdir "*|*"&& mkdir "*|*"|| mkdir "*|*"; rm "*|*"&& rm "*|*"|| rm "*|*"; mv "*|*"&& mv "*|*"|| mv "*|*"; cp "*|*"&& cp "*|*"|| cp "*|*">"*|*">>"*) ;;
        *) return ;;
      esac
      ;;
  esac

  case "$cmd" in
    touch\ *|*"; touch "*|*"&& touch "*|*"|| touch "*|\
    mkdir\ *|*"; mkdir "*|*"&& mkdir "*|*"|| mkdir "*|\
    rm\ *|*"; rm "*|*"&& rm "*|*"|| rm "*|\
    mv\ *|*"; mv "*|*"&& mv "*|*"|| mv "*|\
    cp\ *|*"; cp "*|*"&& cp "*|*"|| cp "*|\
    *">"*|*">>"*) deny_path "$cmd" ;;
  esac
}

case "$tool_name" in
  Edit|Write|MultiEdit|NotebookEdit)
    path="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')"
    [ -z "$path" ] && exit 0
    check_mutation_path "$path"
    ;;
  apply_patch)
    command="$(tool_input_text "command")"
    [ -z "$command" ] && exit 0
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      check_mutation_path "$path"
    done < <(printf '%s\n' "$command" \
      | sed -nE 's/^\*\*\* (Add|Update|Delete) File: (.*)$/\2/p; s/^\*\*\* Move to: (.*)$/\1/p')
    ;;
  Bash|shell|exec_command|unified_exec)
    check_shell_command "$(command_text)" "$(command_workdir)"
    ;;
esac

exit 0
