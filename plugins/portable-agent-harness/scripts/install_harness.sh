#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  install_harness.sh --target <project-path> [--profile base|python] [--with-meta-skills] [--targets codex|claude|all|none] [--adapters codex|claude|all|none] [--with-claude] [--force]

Options:
  --target <path>        Target project root. Required.
  --profile <name>       base or python. Default: base.
  --with-meta-skills     Install evaluate-harness and optimize-harness.
  --targets <value>      Project entrypoints to install. Default: codex.
  --adapters <value>     Backward-compatible alias for --targets.
  --with-claude          Backward-compatible alias for --targets all.
  --force                Overwrite existing files.
  -h, --help             Show this help.
USAGE
}

target=""
profile="base"
with_meta_skills=0
targets="codex"
force=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      target="${2:-}"
      shift 2
      ;;
    --profile)
      profile="${2:-}"
      shift 2
      ;;
    --with-meta-skills)
      with_meta_skills=1
      shift
      ;;
    --targets)
      targets="${2:-}"
      shift 2
      ;;
    --adapters)
      targets="${2:-}"
      shift 2
      ;;
    --with-claude)
      targets="all"
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$target" ]; then
  echo "--target is required" >&2
  usage >&2
  exit 2
fi

if [ "$profile" != "base" ] && [ "$profile" != "python" ]; then
  echo "--profile must be base or python" >&2
  exit 2
fi

if [ "$targets" != "codex" ] && [ "$targets" != "claude" ] && [ "$targets" != "all" ] && [ "$targets" != "none" ]; then
  echo "--targets must be codex, claude, all, or none" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(cd "$script_dir/.." && pwd)"
target_root="$(mkdir -p "$target" && cd "$target" && pwd)"

copy_file() {
  src="$1"
  dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] && [ "$force" -ne 1 ]; then
    echo "skip existing: ${dest#$target_root/}"
    return
  fi
  cp "$src" "$dest"
  echo "installed: ${dest#$target_root/}"
}

copy_tree_files() {
  src_root="$1"
  dest_root="$2"
  [ -d "$src_root" ] || return 0
  find "$src_root" -type f | while IFS= read -r src; do
    rel="${src#$src_root/}"
    copy_file "$src" "$dest_root/$rel"
  done
}

copy_tree_files "$plugin_root/templates/base" "$target_root"

if [ "$profile" = "python" ]; then
  copy_tree_files "$plugin_root/templates/python" "$target_root"
fi

if [ "$with_meta_skills" -eq 1 ]; then
  copy_tree_files "$plugin_root/templates/meta" "$target_root"
fi

if [ "$targets" = "codex" ] || [ "$targets" = "all" ]; then
  copy_file "$plugin_root/templates/codex/AGENTS.md" "$target_root/.codex/AGENTS.md"
fi

if [ "$targets" = "claude" ] || [ "$targets" = "all" ]; then
  copy_file "$plugin_root/templates/claude/CLAUDE.md" "$target_root/CLAUDE.md"
  mkdir -p "$target_root/.claude/rules" "$target_root/.claude/skills"
  find "$target_root/.agents/rules" -maxdepth 1 -type f -name '*.md' | while IFS= read -r rule; do
    name="$(basename "$rule")"
    wrapper="$target_root/.claude/rules/$name"
    if [ -e "$wrapper" ] && [ "$force" -ne 1 ]; then
      echo "skip existing: ${wrapper#$target_root/}"
    else
      printf '@../../.agents/rules/%s\n' "$name" > "$wrapper"
      echo "installed: ${wrapper#$target_root/}"
    fi
  done

  if [ -d "$target_root/.agents/skills" ]; then
    find "$target_root/.agents/skills" -mindepth 1 -maxdepth 1 -type d | while IFS= read -r skill_dir; do
      name="$(basename "$skill_dir")"
      wrapper_dir="$target_root/.claude/skills/$name"
      wrapper="$wrapper_dir/SKILL.md"
      mkdir -p "$wrapper_dir"
      if [ -e "$wrapper" ] && [ "$force" -ne 1 ]; then
        echo "skip existing: ${wrapper#$target_root/}"
      else
        {
          printf '%s\n' '---'
          sed -n '2,/^---$/p' "$skill_dir/SKILL.md" | sed '$d'
          printf '%s\n\n' '---'
          printf '%s\n\n' '# Claude Wrapper'
          printf '%s\n\n' '이 파일은 Claude Code 네이티브 발견을 위한 래퍼입니다. 정본은 Codex 표준 위치에 있습니다.'
          printf '@../../../.agents/skills/%s/SKILL.md\n' "$name"
        } > "$wrapper"
        echo "installed: ${wrapper#$target_root/}"
      fi
    done
  fi
fi

echo "Portable Agent Harness installed into $target_root"
