---
applyTo: "**/*"
---

# 도구 사용 규칙 (절대 규칙)

## 테스트 실행

- **반드시 `execute/runTests` 도구 사용**. 터미널 `pytest` 직접 실행 금지.
- 테스트 파일 경로 명시하여 전체 실행 방지.
- **예외: 커버리지 테스트**는 `uv run pytest --cov` 허용.

## 파일 작업

- **반드시 `create_file`, `replace_string_in_file` 도구 사용**. `cat`/`echo`/heredoc 금지.

## 심볼 리네임

- **반드시 `renameSymbol` 도구 사용**. `sed`/grep 반복 리네임 금지.

## 에러 확인

- **반드시 `get_errors` 도구 사용**. 터미널 linter 실행 금지.

## 터미널 사용

- **패키지 설치(`uv sync`, `uv add`)와 git 명령어**에만 터미널 사용.
- **Python 명령어는 `uv run` 접두사 필수**.
- **멀티라인 따옴표 명령 절대 금지** (`python -c "..."`, heredoc).

## Git 안전 규칙

- **`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean -fd` 금지**.
- **`git add -A`, `git add .` 금지** — 변경한 파일만 명시적으로 스테이지.
- **pre-commit hook 실패 시**: 자동 수정된 파일만 재스테이지 후 재커밋.
- **`git commit`, `git push` 자율 실행 금지** — 사용자가 명시적으로 요청할 때만 실행.

## MCP 쓰기 작업

- **사용자 명시적 승인 후에만** 쓰기 작업 실행. 실행 전 마크다운으로 전체 출력.

## Context7 사용 지침

- **외부 라이브러리 문서**가 필요할 때만 (FastAPI, SQLAlchemy 등 플러그인 개발 시).
- **사용 금지**: 프레임워크 코어, 테스트 작성, 하네스 수정, pytest/ruff 등 안정 도구.

## Mermaid 시각화

- **다이어그램 요청 시 반드시 `renderMermaidDiagram` 도구 사용**. 텍스트 코드블록 출력 금지.
