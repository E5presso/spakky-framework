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

1. **pre-commit hook**: ruff 포맷이 자동 수행되어 커밋이 실패할 수 있음
2. **실패 시**: `git add -A && git commit` 재시도. 절대 `git checkout -- .`나 `git reset --hard` 사용 금지
3. **보호**: 단계마다 커밋하거나 `git stash push -m "백업"` 사용

## MCP 쓰기 작업

GitHub MCP 도구로 쓰기 작업(PR 생성, 이슈 코멘트, 파일 생성 등)을 수행하기 전에:

1. 전체 내용을 마크다운으로 출력
2. 사용자의 명시적 승인을 대기
3. 승인 후에만 도구 호출 실행

### 마크다운 출력 품질 규칙

- 코드 블록 내 ` ``` `이 있으면 외부를 ` ```` `로 감싸기
- `<`, `>` 는 `&lt;`, `&gt;` 또는 인라인 코드로
- 열린 블록이 모두 닫혔는지 확인

## Context7 사용 지침

Context7은 **외부 라이브러리 문서가 필요할 때만** 사용하세요.

**사용하는 경우 (효용 가치 높음):**
- 플러그인 개발 시 외부 라이브러리 문서 참조 (FastAPI, SQLAlchemy, Kafka, RabbitMQ 등)
- 새 라이브러리 버전 마이그레이션
- 학습 데이터 컷오프 이후 업데이트된 API 확인

**사용하지 않는 경우:**
- Spakky 프레임워크 코어 개발 (코드베이스에 이미 있음)
- 테스트 작성 (프로젝트 고유 패턴)
- 하네스/인스트럭션 작성
- pytest, ruff 등 안정적인 도구 (LLM 학습 데이터로 충분)
