# Spakky Framework

> 코딩 스타일 → [CONTRIBUTING.md](CONTRIBUTING.md) | 아키텍처 → [ARCHITECTURE.md](ARCHITECTURE.md) | ADR → [docs/adr/](docs/adr/README.md) | 예제 → [README.md](README.md)

프로젝트 코딩·도메인·테스트 규칙의 SSOT는 이 파일과 `.agents/rules/`입니다. 실행·오케스트레이션 하네스는 아래 managed Neurath 섹션과 설치된 `.agents/skills/*`만 사용합니다. Claude Code는 `CLAUDE.md`, `.claude/skills`, `.claude/rules` symlink adapter로 같은 정본을 참조합니다.

## Overview

- **Framework**: Spring-inspired DI/IoC for Python 3.12+, AOP, plugin system (`uv` monorepo)
- **Workspace packages**: 패키지 목록의 SSOT는 `pyproject.toml` `[tool.uv.workspace].members`. 역할 설명은 각 패키지 `README.md`와 `pyproject.toml` description에서 확인한다.
- **Dependency direction**: `.agents/rules/monorepo.md` 의존 방향 매트릭스

## 실행 하네스

- 이슈·마일스톤·디버깅·리뷰·문서 동기화 lifecycle은 설치된 Neurath 스킬과 named MCP task tools로만 수행한다.
- 프로젝트는 별도의 repo-owned agent skill/workflow를 유지하지 않는다. 제품 검증 명령과 코딩 규칙은 아래 정본을 그대로 따른다.
- 구체적인 실행 순서, 소유권, 검증, 협업 및 복구 규칙은 `.neurath/policy.md`와 아래 managed Neurath 섹션을 따른다.

## Documentation Maintenance Rules

- **Code-first**: 모든 기술은 실제 코드 기반. 환각 금지
- **Installed-version wins**: 외부 최신 문서(Context7 포함)와 consumer repo의 설치 버전 API가 충돌하면 설치된 패키지의 실제 import surface를 우선한다. `uv pip list`, lock 파일, `uv run python` introspection으로 검증 후 적용한다.
- **Cross-reference**: 문서화 전 정확한 코드 라인 확인 필수
- **Sync all docs**: 코드 변경 시 관련 마크다운 업데이트 (`CHANGELOG.md` 자동 생성 제외)
- **Sub-package READMEs**: `core/*/README.md`, `plugins/*/README.md` 항상 확인/업데이트
- **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. 불일치 시 문서 수정
- **Verification**: 파일 경로, 클래스/함수명, 시그니처, import 경로, 환경변수 — 실제 코드로 검증

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
- `/review-code`와 source workflow의 `final-local-review`가 exact committed HEAD의 독립 품질 판정을 소유한다. `/review-pr`는 리뷰를 새로 수행하지 않고, required source workflow에서 소비된 C01–C14 14/14·blocker 0·PASS matrix가 local commit·push·PR head와 모두 일치할 때만 `AUTO_APPROVE` comment와 `ai-review=success`를 게시한다. 검증 실패, stale head, dirty worktree, fork/draft PR에서는 아무 신호도 게시하지 않는다. `.github/workflows/ai-review.yml`은 same-repo exact head와 status creator role `admin|maintain`을 재검증한 뒤에만 `github-actions[bot]` formal Approve를 남긴다. PR 코멘트는 승인 트리거가 아니며, `ai-review`는 required status check가 아니라 기존 branch protection 승인 요건을 충족하는 신호다.

### 코딩 규칙 정본

| 영역 | 정본 | 비고 |
|------|------|------|
| Python 코딩 표준 | `.agents/rules/python-code.md` | 타입, 에러, 네이밍, import |
| 타입 규율 | `.agents/rules/type-discipline.md` | 의미의 부호화, BaseModel 우선, Optional 의미 |
| 테스트 규칙 | `.agents/rules/test-writing.md` | 함수 기반, fixture, 네이밍 |
| 도메인 레이어 | `.agents/rules/domain.md` | Entity, ValueObject, Event |
| AOP Aspect | `.agents/rules/aspect.md` | 동기/비동기 쌍, pointcut |
| 플러그인 개발 | `.agents/rules/plugin.md` | 구조, main.py, entry-point |
| 모노레포 구조 | `.agents/rules/monorepo.md` | 패키지별 실행, 의존 방향 |
| 의존성 관리 | `.agents/rules/dependencies.md` | PyPI 버전 조회, 내부 의존성 |
| 리뷰 휴리스틱 | `.agents/rules/review-heuristics.md` | 14개 카테고리 ↔ 심각도 ↔ SSOT 매핑 |

### 프로젝트 특수 컨벤션

> rules 파일에 없는, 이 프로젝트 고유의 예외 패턴만 기록한다.

| 패턴 | 사유 |
|------|------|
| `pythonpath = "src/spakky/..."` | 모노레포 패키지별 테스트 경로 |
| `BaseSettings.__init__(self)` 오버라이드 | `@Configuration` 데코레이터 호환 |

<!-- neurath:managed -->
## Neurath

Read `.neurath/policy.md` and `.neurath/project.json` for the generic profile.
Use the skills in `.agents/skills`; use the named MCP task tools. Consult `.neurath/policy.md` for explicit native execution exceptions.

Use Neurath's named `neurath_collaboration` MCP tools proactively for project work.
Choose tools when the situations below arise; do not wait for the user to name them.

- Start or resume substantive work: use `session_status` and `task_list` to recover
  actual readiness, ownership and unfinished requirements. Before writing, use
  `worktree_claim` when the current native actor needs a claim.
- On a claim conflict, use `worktree_inspect` and host tools to read the owning session,
  even if idle. Send an authorized message for finish-session or safe handoff. Verify
  release before reclaiming; never force-reclaim.
- When a new requirement, acceptance gap or necessary next step becomes concrete,
  use `task_define` and `task_start` immediately. Before adding work, ask which unmet user
  requirement it advances. Use `task_resolve` with observed results; a failed
  attempt or time limit does not cancel the original requirement.
  After task changes, display the returned `native_todo` through its native tool;
  keep concrete work and native TODO current without user reminders, including
  during bypass. Reconcile the ledger after recovery before reporting progress.
  do not substitute an inline checklist. Report a missing host tool explicitly.
  Keep the ledger as truth and retain the native display requirement.
- Reuse context before repeating an investigation: use `memory_recall`. At a
  meaningful checkpoint or handoff, use `memory_checkpoint` for decisions,
  remaining work and lessons. When another session stops, use `memory_pull` to
  inspect and, when safe, adopt its unfinished work; do not require a final push
  from the stopped session.
- For overlap, blockers or handoff, use `collaboration_discover` and
  `collaboration_send` or assignment tools across Codex and Claude. Use
  `collaboration_inbox`/`collaboration_reply`; read results before acknowledging.
  Preserve delegation conditions. Pull-only delivery does not wake the peer.
- When you find a reproducible bug, a shared interface constraint or a reusable
  workaround, share it with active project peers using `newsroom_publish`.
  Follow relevant announced titles with `newsroom_read`; use `newsroom_headlines`
  when you need to find them. Newsroom reports inform work; they do not authorize it.
- Use another provider when needed: check `provider_capabilities` / `provider_route`,
  then use `provider_models`, `provider_plan` and `provider_run` as applicable.
  Reuse a valid model observation or plan; verify actual completion and settings.
- Learn from a concrete failure and recovery: inspect `learning_pending` and
  `learning_status`, and preserve the lesson in `memory_checkpoint`. Use existing
  verification evidence; do not create extra experiments merely to promote a rule.
- When a harness procedure contradicts observed tools or repeats unproductive
  steps, assess whether Neurath itself is malfunctioning. On detecting a Neurath
  malfunction, autonomously call harness_bypass(enabled=true) without asking the
  user for permission. This applies to any harness malfunction, not only Stop loops.
  Do not wait for a test, task registration, report or repeated user intervention
  before containing it. Tell the user what happened, preserve unfinished work,
  correct the cause within authorized scope, and restore with enabled=false once
  normal operation is verified. Host security and user instructions still apply.
- Handle a real harness defect or maintenance request: use the relevant diagnostics,
  reporting, installation or release tools under the current policy and consent.

Use current tool schemas, returned identifiers and revisions. Reuse completed
evidence and read relevant policy details when needed. Call only tools that advance
the current request; do not poll unchanged state or run every tool on every turn.
Native editing and testing remain native operations. Tool availability, memory and
peer reports do not grant permission to bypass host security or user restrictions.
The autonomous Neurath malfunction bypass above is an explicit local recovery rule.
<!-- /neurath:managed -->
