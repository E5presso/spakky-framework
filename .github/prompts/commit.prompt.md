---
name: commit
description: Spakky Framework 커밋 메시지 작성
tools:
  - search/changes
  - read/readFile
  - search/listDirectory
  - execute/runInTerminal
---

# 커밋 메시지 작성

## Step 1: 변경 사항 확인

`git diff --staged` 또는 `get_changed_files`로 staged 파일을 확인하세요.

## Step 2: Conventional Commits 형식

```
<type>(<scope>): <subject>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Step 3: Scope 결정

변경된 패키지에 해당하는 scope를 사용하세요:

| Scope | 패키지 경로 |
|-------|------------|
| `core` | `core/spakky` |
| `domain` | `core/spakky-domain` |
| `data` | `core/spakky-data` |
| `event` | `core/spakky-event` |
| `fastapi` | `plugins/spakky-fastapi` |
| `kafka` | `plugins/spakky-kafka` |
| `rabbitmq` | `plugins/spakky-rabbitmq` |
| `security` | `plugins/spakky-security` |
| `sqlalchemy` | `plugins/spakky-sqlalchemy` |
| `typer` | `plugins/spakky-typer` |

> **동기화 기준**: `pyproject.toml`의 `[tool.uv.workspace]` members

### Scope 체크리스트

1. **유효성 확인**: 위 테이블에 있는 scope인지 확인
2. **존재하지 않는 scope 발견 시**:
   - 새 패키지 → scope 추가 제안 (CONTRIBUTING.md + 이 파일 업데이트)
   - 오타 → 올바른 scope로 수정 제안
3. **여러 패키지 변경**: 핵심 변경의 scope 사용, 또는 scope 생략

## 예시

```
feat(core): add new scope type
fix(fastapi): resolve routing issue
docs: update contributing guide
refactor(domain,data): extract shared base class
```
