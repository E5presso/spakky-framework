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

$ARGUMENTS
