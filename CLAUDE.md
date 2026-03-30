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

**의존 방향 (단방향):**

```
spakky → spakky-domain → spakky-data → spakky-event → spakky-outbox
spakky → spakky-tracing → spakky-event
spakky → spakky-task
```

## Documentation Maintenance Rules

- **Code-first**: 모든 기술은 실제 코드 기반. 환각 금지
- **Cross-reference**: 문서화 전 정확한 코드 라인 확인 필수
- **Sync all docs**: 코드 변경 시 관련 마크다운 업데이트 (`CHANGELOG.md` 자동 생성 제외)
- **Sub-package READMEs**: `core/*/README.md`, `plugins/*/README.md` 항상 확인/업데이트
- **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. 불일치 시 문서 수정
- **Verification**: 파일 경로, 클래스/함수명, 시그니처, import 경로, 환경변수 — 실제 코드로 검증

## 서브에이전트 활용 전략

모노레포 특성상 독립적인 패키지를 병렬로 작업할 기회가 많습니다. **적극적으로 서브에이전트를 활용**하세요.

### 반드시 서브에이전트를 사용하는 상황

| 상황 | 서브에이전트 활용 |
|------|-----------------|
| **다중 패키지 테스트** | 각 패키지를 별도 서브에이전트로 병렬 실행 |
| **다중 패키지 린트/타입체크** | 패키지별 병렬 검증 |
| **코드 탐색 (3+ 쿼리)** | `Explore` 에이전트로 넓은 범위 탐색 |
| **구현 계획 수립** | `Plan` 에이전트로 설계 → 승인 → 구현 |
| **커버리지 개선** | 파일별 테스트 작성을 병렬 서브에이전트로 분배 |
| **의존성 업데이트 검증** | 패키지별 테스트를 병렬 실행 |
| **리팩터링 영향 분석** | 변경 대상의 사용처를 `Explore`로 탐색 |

### 병렬화 패턴 예시

```
# 여러 패키지 테스트 시
서브에이전트 1: cd core/spakky && uv run pytest
서브에이전트 2: cd core/spakky-data && uv run pytest
서브에이전트 3: cd plugins/spakky-kafka && uv run pytest

# 코드 변경 후 검증 시
서브에이전트 1: 린트 + 타입체크 (해당 패키지)
서브에이전트 2: 유닛 테스트 (해당 패키지)
서브에이전트 3: 영향받는 하위 패키지 테스트
```

### 주의사항

- 같은 파일을 동시에 수정하는 서브에이전트는 금지 (충돌)
- 서브에이전트에게 **완전한 컨텍스트** 제공 (패키지 경로, 실행 명령어, 기대 결과)
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
