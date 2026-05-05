# Spakky Framework

> 코딩 스타일 → [CONTRIBUTING.md](CONTRIBUTING.md) | 아키텍처 → [ARCHITECTURE.md](ARCHITECTURE.md) | ADR → [docs/adr/](docs/adr/README.md) | 예제 → [README.md](README.md)

Codex 표준 에이전트 하네스의 SSOT는 이 파일과 `.agents/rules/`, `.agents/skills/`입니다. Claude Code는 `CLAUDE.md`, `.claude/skills`, `.claude/rules` symlink adapter로 같은 정본을 참조합니다.

## Overview

- **Framework**: Spring-inspired DI/IoC for Python 3.12+, AOP, plugin system (`uv` monorepo)
- **Core** (`core/`): `spakky`, `spakky-domain`, `spakky-data`, `spakky-event`, `spakky-task`, `spakky-tracing`, `spakky-outbox`, `spakky-saga`
- **Plugins** (`plugins/`): `spakky-logging`, `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`, `spakky-celery`, `spakky-opentelemetry`, `spakky-grpc`

## Project Quick Reference

| 경로 | 역할 |
|------|------|
| `core/spakky/` | DI Container, AOP, 부트스트랩 |
| `core/spakky-domain/` | DDD 빌딩 블록 (Entity, AggregateRoot, ValueObject, Event) |
| `core/spakky-data/` | Repository, Transaction 추상화 |
| `core/spakky-event/` | 인프로세스 이벤트 (Publisher, Consumer, EventHandler) |
| `core/spakky-task/` | 태스크 추상화 (스케줄링, 디스패치) |
| `core/spakky-tracing/` | 분산 트레이싱 추상화 (TraceContext, Propagator) |
| `core/spakky-outbox/` | Transactional Outbox 패턴 (OutboxEventBus, Relay) |
| `core/spakky-saga/` | Saga 오케스트레이션 (SagaFlow, SagaStep) |
| `plugins/spakky-fastapi/` | FastAPI REST 컨트롤러 통합 |
| `plugins/spakky-typer/` | Typer CLI 컨트롤러 통합 |
| `plugins/spakky-sqlalchemy/` | SQLAlchemy ORM 통합 |
| `plugins/spakky-rabbitmq/` | RabbitMQ 이벤트 브로커 통합 |
| `plugins/spakky-kafka/` | Kafka 이벤트 브로커 통합 |
| `plugins/spakky-celery/` | Celery 태스크 디스패치 |
| `plugins/spakky-security/` | 암호화/해싱/JWT 유틸리티 |
| `plugins/spakky-logging/` | 구조화 로깅, @logged AOP Aspect |
| `plugins/spakky-opentelemetry/` | OpenTelemetry SDK 브릿지 |

**의존 방향 (단방향):** `.agents/rules/monorepo.md` 참조

## 스킬 & 워크플로우

### 스킬 맵

| 카테고리 | 사용자 호출 | 내부 전용 |
|---------|-----------|----------|
| **plan** | `/plan-issues`, `/audit-spec`, `/impact-analysis` | — |
| **build** | `/autopilot`, `/process-ticket`, `/create-package`, `/checkpoint` | `/commit`, `/create-worktree` |
| **verify** | `/check`, `/improve-coverage`, `/review-code`, `/investigate`, `/property-test`, `/dependency-audit`, `/refactor-code` | — |
| **ship** | — | `/create-pr`, `/triage-comments`, `/monitor-pr`, `/update-project-status` |
| **meta** | `/onboarding`, `/update-dependencies`, `/sync-docs`, `/evaluate-harness`, `/optimize-harness`, `/promote-memory` | `/sync-dev-docs`, `/sync-user-docs` |

### 핵심 워크플로우

```
기획: /plan-issues → 11섹션 SDD spec + Phase 3.5 cold-session 시뮬레이션 → GitHub Issues 생성
스펙 감사: /audit-spec → fresh-slate 8축 재감사 (수렴 3회 상한)
개발: /process-ticket <이슈번호> → 분석 → 계획 → 워크트리 → 구현 → 검증 → 4.5 acceptance-grep → PR → 병합
대량 개발: /autopilot <마일스톤번호> → DAG wave-loop 병렬 처리 → meta-detection (S1-S6)
디버깅: /investigate <증상 또는 이슈번호> → 재현 → 원인 격리 → 수정 후보
검증: /check [패키지] → format → lint → type → test (커버리지 100%)
하네스 진화: /evaluate-harness (선언-실행 단절 감지) → /optimize-harness (5-test) → /promote-memory (메모리 승격)
```

- **이슈 작업은 `/process-ticket`으로 시작한다.** 직접 코딩하지 않는다.
- **마일스톤 단위 작업은 `/autopilot`으로 시작한다.** 단일 티켓은 `/process-ticket`.
- **버그 조사는 `/investigate`로 시작한다.** 가설 없이 코드를 수정하지 않는다.
- **코드 변경 후 문서 동기화는 `/sync-docs`로 수행한다.**
- **하네스 변경 후 `/evaluate-harness`로 회귀 검증.** 5-test 게이트는 `/optimize-harness`.

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

## 절대 금지 사항

> 산재된 금지 규칙의 빠른 참조. 상세는 각 정본 파일 참조.

### Git

- `git checkout -- .`, `git restore .`, `git reset --hard`, `git clean -fd` 금지 — 미커밋 변경 파괴
- `git add -A`, `git add .`는 사용 가능. 단 `.gitignore`되지 않은 임시 파일·민감 정보(`.env`, 비밀키)가 섞일 위험이 있으면 변경한 파일만 명시 스테이지
- PR close/reopen 금지 — CI 실패 시 원인 조사 후 코드 수정하여 재push

### 도구 실행

- **루트에서 ruff/pyrefly/pytest 직접 실행 금지** — 반드시 패키지 디렉토리 내에서
- Python 명령어는 `uv run` 접두사 필수

### 코드

- `src/` 내에서 빌트인 예외(`TypeError`, `ValueError`) 직접 `raise` 금지
- `Any` 타입 사유 없이 사용 금지
- `__str__` 오버라이드 금지 (에러 클래스)
- `src/` 내에서 `assert` 문 금지 — 커스텀 에러로 처리
- 부모 메서드 재정의 시 `@override` 데코레이터 누락 금지
- `getattr()`/`hasattr()`/`setattr()` 사유 없이 사용 금지
- `class TestXxx` 금지 — 함수 기반 테스트만
- Flaky 테스트 금지 — 시간/순서/네트워크 의존 금지
- silent fallback (`pass`, `return None`) 금지
- opt-out 주석(`type: ignore`, `pragma: no cover`) 사유 없이 사용 금지
- 플러그인 → 다른 플러그인 직접 import 금지
- 도메인 레이어에서 인프라 의존성 import 금지

### 행동

- 요청 범위를 넘는 변경 금지 (scope creep)
- 공유 인프라/프레임워크 코어 기술(DI 컨테이너, AOP, 레이어 의존, 빌드 시스템) 교체·제거 시 사용자 확인 필수. 그 외 라이브러리 마이너 교체·내부 구현 리팩터링은 자율 진행
- 가설 없이 코드 수정 금지
- 버그 수정에 리팩터링 혼합 금지

## 도구 사용 규칙

### 터미널

- **Python 명령어는 `uv run` 접두사 필수**
- 패키지 설치(`uv sync`, `uv add`)와 git 명령어에 터미널 사용

### Git 안전 규칙

- **pre-commit hook 실패 시**: 자동 수정된 파일만 재스테이지 후 재커밋

## PR 리뷰 컨벤션

- 리뷰 코멘트는 **한국어**로 작성
- 문제 없으면 PR 승인

## Review guidelines

Codex GitHub code review는 본 섹션을 우선 적용한다. 리뷰는 사소한 스타일보다 실제 운영 결함과 회귀 위험에 집중한다.

- 리뷰 코멘트는 **한국어**로 작성한다.
- P0/P1로 올릴 만한 결함만 남긴다: 런타임 오류, 데이터 손실, 보안 취약점, 레이어 의존 위반, 공개 API 호환성 파괴, 테스트로 잡히지 않는 의미 변경.
- `.agents/rules/review-heuristics.md`의 14개 카테고리를 결함 분류 기준으로 삼고, 지적에는 가능하면 해당 SSOT를 언급한다.
- Python `src/` 변경에서는 빌트인 예외 직접 `raise`, 사유 없는 `Any`, `assert`, `type: ignore`, `getattr()`/`hasattr()`/`setattr()` 사용을 P1 후보로 검토한다.
- 테스트 변경에서는 `class TestXxx`, flaky 시간/순서/네트워크 의존, 커버리지 회피 주석, 실제 회귀를 검증하지 않는 스냅샷성 테스트를 P1 후보로 검토한다.
- 모노레포 의존 방향을 확인한다. 플러그인 간 직접 import, 도메인 레이어의 인프라 import, core와 plugin의 역방향 의존은 P1 후보로 검토한다.
- 코드 변경이 문서와 불일치하면 관련 Markdown 동기화 누락을 지적한다. 특히 public API, 환경변수, 패키지 README, `ARCHITECTURE.md`, `CONTRIBUTING.md` 불일치를 확인한다.
- 단순 취향, 네이밍 선호, 포맷터가 처리할 내용, 현재 PR이 만들지 않은 pre-existing 문제는 리뷰를 남기지 않는다. 단, 새 변경이 기존 문제를 활성화하거나 악화하면 지적한다.
- 제안은 최소 수정 단위로 작성한다. 리팩터링 제안은 실제 결함을 제거하거나 중복된 위험을 줄일 때만 남긴다.
- 리뷰가 통과 가능하더라도 GitHub formal Approve를 자동 승인 게이트로 가정하지 않는다. 사람 승인 또는 branch protection은 별도 정책으로 남긴다.

### 코딩 규칙 정본

| 영역 | 정본 | 비고 |
|------|------|------|
| **에이전트 헌장** | `.agents/rules/charter.md` | 정책→비즈니스→코드 위계, 3-축 정렬, 7차원 품질 바, 외부 게이트 |
| Python 코딩 표준 | `.agents/rules/python-code.md` | 타입, 에러, 네이밍, import |
| 타입 규율 | `.agents/rules/type-discipline.md` | 의미의 부호화, BaseModel 우선, Optional 의미 |
| 테스트 규칙 | `.agents/rules/test-writing.md` | 함수 기반, fixture, 네이밍 |
| 도메인 레이어 | `.agents/rules/domain.md` | Entity, ValueObject, Event |
| AOP Aspect | `.agents/rules/aspect.md` | 동기/비동기 쌍, pointcut |
| 플러그인 개발 | `.agents/rules/plugin.md` | 구조, main.py, entry-point |
| 모노레포 구조 | `.agents/rules/monorepo.md` | 패키지별 실행, 의존 방향 |
| 행동 원칙 | `.agents/rules/behavioral-guidelines.md` | Karpathy 4원칙, Simplicity 시그널, 자가 질의 검사 |
| 의존성 관리 | `.agents/rules/dependencies.md` | PyPI 버전 조회, 내부 의존성 |
| 리뷰 휴리스틱 | `.agents/rules/review-heuristics.md` | 14개 카테고리 ↔ 심각도 ↔ SSOT 매핑 |
| 하네스 작성 | `.agents/rules/harness-writing.md` | 5-Test 게이트, 토큰=비용, 역사 박제 금지 |
| 스킬 작성 | `.agents/rules/write-skill.md` | 워크트리 격리, 스크립트 테스트 의무 |

### 프로젝트 특수 컨벤션

> rules 파일에 없는, 이 프로젝트 고유의 예외 패턴만 기록한다.

| 패턴 | 사유 |
|------|------|
| `pythonpath = "src/spakky/..."` | 모노레포 패키지별 테스트 경로 |
| `BaseSettings.__init__(self)` 오버라이드 | `@Configuration` 데코레이터 호환 |
