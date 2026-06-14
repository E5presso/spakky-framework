# Phase 3: 워크트리 생성

> **절대 규칙: 워크트리 없이 구현을 시작하지 않는다.**
> Phase 4 이후의 모든 파일 수정은 반드시 워크트리 절대경로 안에서 수행해야 한다.
> 루트 리포지토리를 직접 수정하면 develop 브랜치가 오염된다.
> **워크트리 생성을 건너뛰는 것은 어떤 상황에서도 허용되지 않는다.**

> **Phase 진입 ping** (sub-agent 한정): `git worktree add` 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 3 worktree | issue: <id> | worktree created at <abs-path>`). SKILL.md "Phase 전환 progress ping" SSOT.

사용자가 계획을 승인하면 (또는 기본값인 승인 생략 시 Phase 2-2 완료 후 즉시):

1. 이슈 내용에 따라 접두어(prefix)를 결정한다: `feat`, `fix`, `refactor`, `docs`, `hotfix` 등.
2. `/create-worktree {prefix} {ISSUE-NUMBER}` 서브스킬을 실행한다. 본 서브스킬은 메인 세션에서 `git worktree add <abs-path> -b <branch> origin/develop`로 워크트리를 만들고 **워크트리 절대경로** `WORKTREE_ABS`를 반환한다. **`EnterWorktree` 도구 호출 금지** — 도구가 부모/형제 sub-agent 프로세스 cwd를 변이시켜 hook 판정과 인접 작업이 깨진다.
3. 반환된 `WORKTREE_ABS`를 후속 모든 도구 호출의 절대경로로 사용한다. sub-agent 프롬프트는 이 절대경로를 인자로 받아 자기 워크트리만 인지한다.
4. **Bash·git·파일 도구 호출 컨벤션 (모든 후속 phase 의무)**: `.agents/rules/worktree-isolation.md` §3 컨벤션 의무.
5. **생성 확인 후에만** Phase 4로 진행한다. `git -C "$WORKTREE_ABS" rev-parse --show-toplevel`이 `$WORKTREE_ABS`와 일치하지 않으면 즉시 중단하고 사용자에게 보고한다.
6. **체크포인트 초기화** — 워크트리 루트(`$WORKTREE_ABS/.process-state.json`)에 메타 필드를 채운다 (SKILL.md "상태 핸드오프" 참조):
   ```bash
   ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   cat > "$WORKTREE_ABS/.process-state.json" <<EOF
   {"issue_number": "{ISSUE-NUMBER}", "worktree": "$WORKTREE_ABS", "updated_at": "$ts"}
   EOF
   ```
7. **이슈/프로젝트 상태 갱신 (명시적 호출 — silent 누락 금지)** — 서브에이전트로 `/update-project-status {ISSUE-NUMBER} In Progress` 실행. 결과 stdout 1줄을 반드시 회수한다:
   - 성공(`이슈 ... 상태 -> In Progress`) 출력 확인 시 진행.
   - 실패·경고(`갱신 실패`·매칭 상태 없음 등) 관찰 시 메인 stdout에 `project-status-update-failed: In Progress <원인>` 1줄 기록 후 본 스킬의 최종 반환 `notes:` 라인에 동일 메시지를 누적한다 (본 작업은 차단하지 않음 — SKILL.md "GitHub Issue 상태 자동 전이" 참조).
