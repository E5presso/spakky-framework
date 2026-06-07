---
name: commit
description: Spakky Framework 커밋 메시지를 Conventional Commits 형식으로 작성합니다
argument-hint: "[추가 설명]"
user-invocable: true
---

# 커밋 메시지 작성

Conventional Commits 형식: `<type>(<scope>): <subject>`

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Scope는 변경된 workspace member에서 도출한다: `pyproject.toml` `[tool.uv.workspace].members`가 SSOT이며 `spakky-` 접두사는 제거한다. 예외: `core/spakky`는 `core`. 여러 패키지 변경은 핵심 패키지 scope를 쓰거나 scope를 생략한다.

## 워크플로우

1. 변경된 패키지 디렉토리에서 `uv run ruff format .` 선행 (pre-commit hook 실패 방지)
2. `git diff --cached`로 스테이지된 변경 확인
3. 변경 내용 분석 후 적절한 type, scope, subject 결정
4. 커밋 메시지를 결정하고 **자동 커밋** 실행 (사용자 승인 불필요)

$ARGUMENTS
