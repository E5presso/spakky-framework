---
description: GitHub Issue 번호를 받아 develop 최신화 → 워크트리 생성 → 브랜치 설정까지 수행합니다.
argument-hint: "<prefix> <issue-number>"
user-invocable: false
---

# Create Worktree — 워크트리 생성 서브스킬

GitHub Issue 번호와 접두어(prefix)를 받아 워크트리를 생성한다. **메인 세션에서만 호출** — sub-agent는 워크트리 절대경로를 인자로 받아 사용하며 본 스킬을 직접 호출하지 않는다.

## 사용법

상위 스킬에서 호출:

```
/create-worktree feat 42
```

인자: `<prefix> <issue-number>`
- prefix: git workflow 접두어 (`feat`, `fix`, `refactor`, `docs`, `hotfix` 등). 워크트리 디렉토리명에는 사용되지 않으며, 호출자가 브랜치명 컨벤션을 일치시키는 용도다.
- issue-number: GitHub Issue 번호 (예: `42`, `1234`)

## 절차

1. **이름 생성**:
   - **워크트리명**: `{prefix}-{issue-number}` (하이픈) — 예: `feat-42`
   - **브랜치명**: `{prefix}/{issue-number}` (슬래시) — 예: `feat/42`

2. **repo 절대경로 도출**:
   ```bash
   REPO_ROOT=$(git -C <호출자 cwd 또는 루트 체크아웃 임의 경로> rev-parse --path-format=absolute --git-common-dir | sed 's|/\.git$||')
   WORKTREE_ABS="$REPO_ROOT/.claude/worktrees/{워크트리명}"
   ```
   `<repo_root>/.claude/worktrees/`가 표준 위치다. 다른 위치 사용 금지 — `check-worktree-isolation.sh`가 이 prefix로 워크트리 소속을 판정한다.

3. **develop 최신화**:
   ```bash
   git -C "$REPO_ROOT" fetch origin develop
   ```

4. **워크트리 생성** (`EnterWorktree` 도구 사용 금지 — cwd 드리프트 회귀 원인):
   ```bash
   git -C "$REPO_ROOT" worktree add "$WORKTREE_ABS" -b {prefix}/{issue-number} origin/develop
   ```
   기존 브랜치가 이미 있으면 `-b` 대신 `git worktree add "$WORKTREE_ABS" {prefix}/{issue-number}`로 진입한다. 기존 브랜치에 미병합 커밋이 있으면 삭제하지 말고 중단한다.

5. **생성 확인**:
   ```bash
   git -C "$WORKTREE_ABS" rev-parse --show-toplevel  # → $WORKTREE_ABS 동일해야 함
   git -C "$WORKTREE_ABS" branch --show-current      # → {prefix}/{issue-number}
   ```
   확인 실패 시 즉시 중단하고 호출자에게 오류를 반환한다.

6. **반환값**: 호출자에게 워크트리 **절대경로** `$WORKTREE_ABS` 를 명시적으로 반환한다. 후속 phase (Phase 4 구현, Phase 5 commit, Phase 8 cleanup)는 이 절대경로를 모든 도구 호출 인자에 직접 사용한다. 호출자가 본 절대경로를 sub-agent prompt에 명시 인자로 전달하여 sub-agent가 자기 워크트리만 인지하도록 한다 (형제 격리는 컨벤션 의존 — `worktree-isolation.md` 참조).

$ARGUMENTS
