---
name: create-worktree
description: 이슈 번호와 접두어를 받아 source 브랜치 최신화 → 워크트리 생성 → 브랜치 이름 설정까지 수행합니다.
argument-hint: "<prefix> <issue-number>"
user-invocable: false
---

# Create Worktree — 워크트리 생성 서브스킬

이슈 번호와 접두어(prefix)를 받아 워크트리를 생성한다.

## 사용법

서브에이전트에서 호출:

```
/create-worktree feat 42
```

인자: `<prefix> <issue-number>`
- prefix: git workflow 접두어 (`feat`, `fix`, `refactor`, `docs`, `hotfix`, `release` 등)
- issue-number: GitHub Issue 번호

## 절차

1. **이름 생성**:
   - **워크트리명**: `{prefix}-{issue-number}` (하이픈) — 예: `feat-42`
   - **브랜치명**: `{prefix}/{issue-number}` (슬래시) — 예: `feat/42`

2. **source 브랜치 최신화**:
   ```bash
   git fetch origin develop
   ```

3. **워크트리 생성**:
   - `EnterWorktree`의 `name` 파라미터에 워크트리명(`feat-42`)을 전달한다.

4. **develop 기준으로 리셋**:
   - `EnterWorktree`는 세션의 원래 HEAD에서 워크트리를 만든다. 워크트리 진입 후 develop으로 맞춘다:
     ```bash
     git reset --hard origin/develop
     ```

5. **브랜치명 변경**:
   - 워크트리 생성 후 브랜치명을 `{prefix}/{issue-number}`로 변경한다:
     ```bash
     git branch -m {prefix}/{issue-number}
     ```
   - 이전 작업으로 같은 이름의 브랜치가 남아 실패하면, `git log origin/develop..{prefix}/{issue-number}`로 미병합 커밋 유무를 확인한 후 없을 때만 `git branch -D`로 삭제하고 재시도한다.

## ⚠️ 워크트리 진입 후 필수 확인 (루트 오염 방지)

`EnterWorktree`가 세션의 CWD를 워크트리로 바꾸더라도, **Read/Edit/Write 도구에 전달하는 절대 경로는 바뀌지 않는다.** 도구 호출에서 무심코 `/Users/.../spakky-framework/core/...` (루트 리포 경로)를 쓰면 **develop 브랜치가 오염된다.**

Phase 4~5의 첫 파일 수정 직전에 반드시 다음을 수행한다:

1. **워크트리 절대 경로 확보**: `pwd` → `.claude/worktrees/{prefix}-{issue-number}`로 끝나야 함.
2. **파일 수정 시 상대 경로 우선**. CWD가 워크트리이므로 상대 경로(`core/spakky-saga/src/...`)는 자동으로 올바른 위치를 가리킨다.
   - ✗ `/Users/.../spakky-framework/core/...` (루트 — 금지)
   - ✓ `core/spakky-saga/src/...` (상대 — 권장)
   - ✓ `/Users/.../spakky-framework/.claude/worktrees/{name}/core/...` (워크트리 절대)
3. **첫 Edit 직후 `git status`로 검증**한다. 워크트리의 `git status`가 변경을 보이지 않으면 루트에 쓴 것이다 — 즉시 루트 변경을 되돌리고 올바른 경로로 다시 쓴다.

$ARGUMENTS
