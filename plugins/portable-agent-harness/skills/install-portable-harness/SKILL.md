---
name: install-portable-harness
description: 새 프로젝트에 Portable Agent Harness payload를 설치하고 Codex 또는 Claude Code의 표준 프로젝트 entrypoint를 생성합니다.
argument-hint: "--target <project-path> [--profile base|python] [--with-meta-skills] [--targets codex|claude|all|none] [--force]"
user-invocable: true
---

# Install Portable Harness

새 프로젝트에 공용 하네스 payload를 설치하고, 선택한 에이전트별 표준 프로젝트 entrypoint를 생성한다. `.agents/`가 정본이고, `.codex/`와 `.claude/`는 대상 프로젝트에서만 생성되는 얇은 참조 계층이다.

## 사용법

```bash
./plugins/portable-agent-harness/scripts/install_harness.sh --target . --profile python --with-meta-skills --targets all
```

## 옵션

- `--target <path>`: 설치 대상 프로젝트 루트. 필수.
- `--profile base|python`: 기본값 `base`. `python`은 Python 코딩/테스트/타입 규칙을 추가한다.
- `--with-meta-skills`: `evaluate-harness`, `optimize-harness` 스킬을 함께 설치한다.
- `--targets codex|claude|all|none`: 생성할 프로젝트 entrypoint를 선택한다. 기본값은 `codex`.
- `--adapters codex|claude|all|none`: 이전 호출 호환용 alias. `--targets`와 같다.
- `--with-claude`: 이전 호출 호환용 alias. `--targets all`과 같다.
- `--force`: 기존 파일을 덮어쓴다. 없으면 기존 파일을 보존한다.

## 설치 후 수동 작업

1. 대상 프로젝트의 `AGENTS.md`에서 TODO를 실제 프로젝트 구조로 교체한다.
2. 프로젝트 전용 규칙은 `.agents/rules/`에 별도 파일로 추가한다.
3. 프로젝트 전용 스킬은 `.agents/skills/`에 추가한다.
4. entrypoint 포인터 검증을 실행한다:

```bash
find .agents .codex .claude -type f | sort
```

## 규칙

- 설치 스크립트는 `.agents/`를 정본으로 유지한다.
- 기존 하네스가 있으면 `--force` 없이는 덮어쓰지 않는다.
- 프로젝트 전용 내용은 템플릿에 박제하지 않는다. 대상 프로젝트의 `AGENTS.md`와 별도 rules/skills에서 작성한다.

$ARGUMENTS
