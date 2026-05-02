# Spakky Framework Agent Harness

이 파일은 Codex와 Claude Code가 함께 읽는 공용 진입점이다. 하네스의 단일 원본은 `.agents/harness/`이며, 도구별 디렉터리(`.claude/`, `.codex/`)는 얇은 어댑터로만 둔다.

## 공용 하네스 구조

| 경로 | 역할 |
|------|------|
| `.agents/harness/rules/` | 에이전트 공통 정책·코딩·테스트·문서 규칙 |
| `.agents/harness/skills/` | 재사용 워크플로우 원본 |
| `.claude/rules/` | Claude Code 네이티브 규칙 래퍼 |
| `.claude/skills/` | Claude Code 네이티브 스킬 래퍼 |
| `.codex/AGENTS.md` | Codex 네이티브 진입 래퍼 |
| `CLAUDE.md` | Claude Code용 프로젝트 요약 |
| `AGENTS.md` | Codex용 진입점 (`@RTK.md`) |

## 작업 원칙

- 프로젝트 규칙은 `.agents/harness/rules/*.md`를 정본으로 삼는다.
- 스킬·워크플로우는 `.agents/harness/skills/*/SKILL.md`를 정본으로 삼는다.
- `.claude/rules` 또는 `.claude/skills`에 새 규칙을 추가하지 않는다. 필요한 경우 공용 하네스에 추가한다.
- 도구별 차이가 필요한 내용만 `.claude/` 또는 `.codex/`에 둔다.
- Python 명령은 `uv run` 접두사를 사용한다.
- 루트에서 ruff/pyrefly/pytest를 직접 실행하지 않는다. 패키지 디렉터리 안에서 실행한다.

## 빠른 참조

- 코딩 스타일: `CONTRIBUTING.md`
- 아키텍처: `ARCHITECTURE.md`
- 모노레포 의존 방향: `.agents/harness/rules/monorepo.md`
- Python 규칙: `.agents/harness/rules/python-code.md`
- 테스트 규칙: `.agents/harness/rules/test-writing.md`
- 하네스 작성 규칙: `.agents/harness/rules/harness-writing.md`

## 프로젝트 금지 사항

- `git checkout -- .`, `git restore .`, `git reset --hard`, `git clean -fd` 금지.
- `src/` 내 빌트인 예외 직접 `raise`, 사유 없는 `Any`, 사유 없는 opt-out 주석 금지.
- 테스트는 함수 기반으로 작성한다. `class TestXxx` 금지.
- 플러그인에서 다른 플러그인을 직접 import하지 않는다.
- 도메인 레이어에서 인프라 의존성을 import하지 않는다.
- 코드 변경과 무관한 리팩터링을 섞지 않는다.
