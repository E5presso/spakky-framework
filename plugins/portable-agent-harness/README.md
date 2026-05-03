# Portable Agent Harness

Portable agent harness templates extracted from Spakky Framework for reuse in new projects.

This plugin follows each host's native plugin layout:

- Codex: `.codex-plugin/plugin.json`
- Claude Code: `.claude-plugin/plugin.json`
- Shared plugin components: root-level `skills/`

The install skill writes a project-local harness payload into a target repository:

- `AGENTS.md`
- `.agents/rules/`
- optional `.agents/skills/` meta skills
- optional project-local entrypoints for Codex and Claude Code

## Install Into A Project

From this plugin directory:

```bash
./scripts/install_harness.sh --target /path/to/project --profile python --with-meta-skills --targets all
```

Use `--force` to overwrite existing harness files. Without `--force`, existing files are preserved.

Target entrypoint options:

- `--targets codex`: install `.codex/AGENTS.md`. This is the default.
- `--targets claude`: install `CLAUDE.md` and `.claude/` wrappers.
- `--targets all`: install both Codex and Claude Code project entrypoints.
- `--targets none`: install only the shared `.agents` payload.

`--adapters` remains as a backward-compatible alias for `--targets`, but the plugin no longer uses a custom adapter directory.

## Profiles

- `base`: portable behavior, review, documentation, harness-writing, and skill-writing rules.
- `python`: `base` plus Python typing, coding, and test-writing rules.

## Boundaries

This plugin intentionally excludes Spakky-specific package maps, monorepo dependency rules, release workflows, and product-specific skills. Add those in the target project's `AGENTS.md` after installation.
