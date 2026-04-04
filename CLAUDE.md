# Spakky Framework

> 코딩 스타일 → [CONTRIBUTING.md](CONTRIBUTING.md) | 아키텍처 → [ARCHITECTURE.md](ARCHITECTURE.md) | ADR → [docs/adr/](docs/adr/README.md) | 예제 → [README.md](README.md)

## Overview

- **Framework**: Spring-inspired DI/IoC for Python 3.11+, AOP, plugin system (`uv` monorepo)
- **Core** (`core/`): `spakky`, `spakky-domain`, `spakky-data`, `spakky-event`, `spakky-task`, `spakky-tracing`, `spakky-outbox`
- **Plugins** (`plugins/`): `spakky-logging`, `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`, `spakky-celery`

## Project Quick Reference

| 경로 | 역할 |
|------|------|
| `core/spakky/` | DI Container, AOP, 부트스트랩 |
| `core/spakky-domain/` | DDD 빌딩 블록 |
| `core/spakky-data/` | Repository, Transaction 추상화 |
| `core/spakky-event/` | 인프로세스 이벤트 |
| `core/spakky-task/` | 태스크 추상화 (스케줄링, 디스패치) |
| `plugins/spakky-*/` | 플러그인 구현체 |

**의존 방향 (단방향):** `.claude/rules/monorepo.md` 참조

## Documentation Maintenance Rules

- **Code-first**: 모든 기술은 실제 코드 기반. 환각 금지
- **Cross-reference**: 문서화 전 정확한 코드 라인 확인 필수
- **Sync all docs**: 코드 변경 시 관련 마크다운 업데이트 (`CHANGELOG.md` 자동 생성 제외)
- **Sub-package READMEs**: `core/*/README.md`, `plugins/*/README.md` 항상 확인/업데이트
- **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. 불일치 시 문서 수정
- **Verification**: 파일 경로, 클래스/함수명, 시그니처, import 경로, 환경변수 — 실제 코드로 검증

## 서브에이전트 활용

서브에이전트 바이어스 원칙은 `behavioral-guidelines.md` §5 참조. 모노레포 특성상 패키지별 병렬 작업에 특히 유효합니다.

### 주의사항

- 같은 파일을 동시에 수정하는 서브에이전트는 금지 (충돌)
- `worktree` 격리 모드는 파일 수정이 필요한 독립 작업에 활용

## 도구 사용 규칙

### 터미널

- **Python 명령어는 `uv run` 접두사 필수**
- 패키지 설치(`uv sync`, `uv add`)와 git 명령어에 터미널 사용

### Git 안전 규칙

- **`git checkout -- .`, `git restore .`, `git reset --hard`, `git clean -fd` 금지**
- **`git add -A`, `git add .` 금지** — 변경한 파일만 명시적으로 스테이지
- **pre-commit hook 실패 시**: 자동 수정된 파일만 재스테이지 후 재커밋
- **`git commit`, `git push` 자율 실행 금지** — 사용자가 명시적으로 요청할 때만 실행

## PR 리뷰 컨벤션

- 리뷰 코멘트는 **한국어**로 작성
- 문제 없으면 PR 승인

### 프로젝트 컨벤션

| 패턴 | 사유 |
|------|------|
| `pythonpath = "src/spakky/..."` | 모노레포 패키지별 테스트 경로 |
| `# type: ignore[xxx]  # reason` | 에러 코드 + 사유 명시 시 허용 |
| Integration fixture `scope="package"` | 비용 절감 |
| `BaseSettings.__init__(self)` 오버라이드 | `@Configuration` 데코레이터 호환 |

### 리뷰 포인트

- `# type: ignore` 사용 시 에러 코드와 사유 명시 권장
- `Any` 타입 사용 시 사유 명시 권장
- 명시적 에러 처리 권장 (`raise` 또는 `assert_never`)
