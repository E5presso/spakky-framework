---
applyTo: "**/*"
---

# 도구 사용 규칙 (절대 규칙)

## 테스트 실행

- **반드시 `execute/runTests` 도구를 사용**하세요. 터미널에서 `pytest`를 실행하지 마세요.
- 테스트 파일 경로를 명시하여 불필요한 전체 실행을 피하세요.
- **예외: 커버리지 테스트**는 터미널에서 `uv run pytest --cov` 실행을 허용합니다.

## 파일 작업

- **반드시 `create_file`, `replace_string_in_file` 도구를 사용**하세요.
- 터미널에서 `cat`, `echo`, heredoc으로 파일을 생성/수정하지 마세요.

## 에러 확인

- **반드시 `get_errors` 도구를 사용**하세요. 터미널에서 linter를 실행하지 마세요.

## 터미널 사용

- 터미널은 **패키지 설치(`uv sync`, `uv add`)와 git 명령어**에만 사용하세요.
- Python 명령어는 반드시 `uv run` 접두사를 붙이세요.
- 멀티라인 따옴표 명령(`python -c "..."`, heredoc)은 **절대 사용 금지**입니다.

## Git 안전 규칙

**파괴적 Git 명령어 금지:**
- `git checkout -- .` — 모든 unstaged 변경 삭제
- `git restore .` — 모든 unstaged 변경 삭제
- `git reset --hard` — 커밋되지 않은 모든 변경 삭제
- `git clean -fd` — untracked 파일 삭제

특정 파일만 되돌려야 할 경우 **파일 경로를 명시**하세요:
```bash
# ✅ 올바른 예: 특정 파일만
git checkout -- path/to/specific/file.py

# ❌ 금지: 전체 작업 디렉토리
git checkout -- .
```

## 커밋 워크플로우

**커밋은 의미 있는 작업 단위로 나눠서 진행하세요.**

1. **pre-commit hook**: 커밋 시 ruff 포맷이 자동 수행되어 커밋이 실패할 수 있음
2. **실패 시 대응**: 당황하여 staged 변경사항을 날려먹지 말 것
   - `git add -A && git commit` 재시도
   - 절대로 `git checkout -- .`나 `git reset --hard` 사용 금지

**변경사항 보호 전략:**
- 단계마다 미리 커밋해두기 (권장)
- 불안하면 `git stash push -m "백업"` 으로 백업
- 긴 작업 전 `git stash push --keep-index -m "안전망"` 사용

```bash
# pre-commit 실패 시 올바른 복구
git add -A
git commit -m "same message"

# 작업 백업 (긴 작업 전)
git stash push -m "WIP: 작업 백업"
```

## MCP 쓰기 작업

GitHub MCP 도구로 쓰기 작업(PR 생성, 이슈 코멘트, 파일 생성 등)을 수행하기 전에:

1. 전체 내용을 마크다운으로 출력
2. 사용자의 명시적 승인을 대기
3. 승인 후에만 도구 호출 실행
