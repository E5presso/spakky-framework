# Spakky Framework - AI Coding Instructions

> **컨텍스트 로딩 (필요 시)**:
> - 코딩 스타일/네이밍 → [CONTRIBUTING.md](../CONTRIBUTING.md)
> - 아키텍처/이벤트 시스템 → [ARCHITECTURE.md](../ARCHITECTURE.md)
> - API 사용 예제 → [README.md](../README.md)

## Overview

Spring-inspired DI/IoC framework for Python 3.11+ with AOP and plugin system. Uses `uv` workspace monorepo.

- **Core** (`core/`): `spakky`, `spakky-domain`, `spakky-data`, `spakky-event`
- **Plugins** (`plugins/`): `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`

## Documentation Maintenance Rules

**This section MUST be preserved in all future versions.**

1. **Code-first**: Every statement must be backed by actual code. No hallucinations.
2. **Cross-reference**: Find the exact code line before documenting any feature.
3. **Sync all docs**: Changes to codebase → update all relevant markdown files (NOT `CHANGELOG.md`, it's auto-generated).
4. **Sub-package READMEs**: Always check/update READMEs in all `core/*/README.md` and `plugins/*/README.md`.
5. **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. If docs contradict code, update docs.
6. **Verification checklist**: File paths, class/function names, method signatures, import paths, env var prefixes — all must be verified against actual code.
