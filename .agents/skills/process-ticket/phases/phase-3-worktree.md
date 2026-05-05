# Phase 3: 워크트리 생성

> **절대 규칙: 워크트리 없이 구현을 시작하지 않는다.**
> Phase 4 이후의 모든 파일 수정은 반드시 워크트리 내에서 수행해야 한다.
> 루트 리포지토리에서 직접 코드를 수정하면 develop 브랜치가 오염된다.
> **워크트리 생성을 건너뛰는 것은 어떤 상황에서도 허용되지 않는다.**

> **Phase 진입 ping** (sub-agent 한정): EnterWorktree 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 3 worktree | issue: <N> | worktree entered`). SKILL.md "Phase 전환 progress ping" SSOT.

사용자가 계획을 승인하면 (또는 기본값인 승인 생략 시 Phase 2-2 완료 후 즉시):

1. 이슈 내용에 따라 접두어(prefix)를 결정한다: `feat`, `fix`, `refactor`, `docs`, `hotfix`, `chore` 등
2. `/create-worktree {prefix} {ISSUE-NUMBER}` 서브스킬을 실행한다. 워크트리 디렉터리는 `feat-<N>` 형식, 브랜치는 `feat/<N>` 형식.
3. **`EnterWorktree`가 완료되었음을 확인한 후에만** Phase 4로 진행한다. 워크트리 진입에 실패하면 즉시 중단하고 사용자에게 보고한다.
4. **체크포인트 초기화** — 워크트리 루트(`<worktree>/.process-state.json`)에 메타 필드를 채운다 (SKILL.md "상태 핸드오프" 참조):
   ```bash
   ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   wt=$(pwd)
   cat > "$wt/.process-state.json" <<EOF
   {"issue_number": {ISSUE-NUMBER}, "worktree": "$wt", "updated_at": "$ts"}
   EOF
   ```
5. **root-worktree mutation guard 초기화 (기계적 차단)** — 체크포인트 생성 직후, 구현 파일을 하나라도 수정하기 전에 다음 스크립트를 워크트리 cwd에서 실행한다:
   ```bash
   bash .agents/skills/process-ticket/scripts/assert_worktree_isolation.sh --init {ISSUE-NUMBER}
   ```
   이 스크립트는 (a) 현재 cwd가 루트 리포지토리가 아니라 `.claude/worktrees/<prefix>-<N>` 아래인지, (b) 브랜치가 `*/<N>`인지, (c) 루트 리포지토리 브랜치가 `develop`이며 dirty 상태가 아닌지 검증하고, 루트 HEAD/status digest를 `.process-state.json.root_guard`에 기록한다. 실패하면 Phase 4 진입 금지. root dirty를 자동 되돌리지 않는다 — 다른 세션의 변경일 수 있으므로 `isolation-failed: ...`를 보고하고 중단한다.
6. **프로젝트 상태 갱신 (명시적 호출 — silent 누락 금지)** — 서브에이전트로 `/update-project-status {ISSUE-NUMBER} "In Progress"` 실행. 결과 stdout 1줄을 반드시 회수한다:
   - 성공(`이슈 #N 상태 -> In Progress`) 출력 확인 시 진행.
   - 실패·경고(`갱신 실패`·매칭 상태 없음 등) 관찰 시 메인 stdout에 `project-status-update-failed: In Progress <원인>` 1줄 기록 후 본 스킬의 최종 반환 `notes:` 라인에 동일 메시지를 누적한다 (본 작업은 차단하지 않음 — SKILL.md "GitHub 이슈/프로젝트 상태 자동 전이" 참조).
