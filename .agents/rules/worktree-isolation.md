# 워크트리 격리 (sub-agent cwd 드리프트 방지)

Codex multi-agent 실행에서 sub-agent들은 부모/형제와 동일한 OS 프로세스 cwd를 공유할 수 있다. 따라서 cwd를 변이시키는 도구·명령은 동시에 진행 중인 형제 sub-agent의 hook 판정·파일 도구 호출을 동시에 깬다. 본 규칙은 그 원인을 제거한다.

## 1. `EnterWorktree` / `ExitWorktree` 도구 호출 금지

- 워크트리 생성은 메인 세션이 `git -C <repo-root> worktree add <repo-root>/.claude/worktrees/<branch> -b <branch> origin/develop`로 직접 수행한다.
- 워크트리 정리는 메인 세션이 `git -C <repo-root> worktree remove <abs-path> --force`로 직접 수행한다.
- sub-agent는 어떤 phase에서도 `EnterWorktree`·`ExitWorktree` 도구를 호출하지 않는다 (해당 prompt에 부재).

## 2. sub-agent는 워크트리 절대경로를 인자로 받는다

- 메인 세션이 spawn prompt에 워크트리 절대경로 `WORKTREE_ABS`를 명시 인자로 박는다.
- sub-agent는 자기 절대경로 외 경로를 spawn prompt 어디에서도 인지하지 않는다 — 형제 격리는 본 컨벤션 의존이다 (hook 강제 불가, §5 참조).
- sub-agent가 발견된 다른 worktree 경로(예: `git worktree list` 출력)에 도구 호출을 보내는 것은 본 규칙 위반.

## 3. cwd 무변이 Bash·파일 도구 호출 컨벤션

sub-agent의 모든 Bash·파일 도구 호출은 부모 프로세스 cwd를 변이시키지 않는 형식을 사용한다:

- **git 명령**: `git -C "$WORKTREE_ABS" <subcommand>` — `-C` 플래그가 명령 단위로 작업 디렉토리를 지정한다.
- **그 외 명령**: `(cd "$WORKTREE_ABS" && <cmd>)` 서브쉘로 cd를 격리하거나 `cd "$WORKTREE_ABS" && <cmd>` 단일 Bash tool_use 인라인 패턴 (단일 호출 안에서 cd가 끝난다).
- **Edit/Write/Read**: `file_path` 인자에 `"$WORKTREE_ABS/..."` 절대경로를 직접 사용한다.
- **bare `cd <abs-path>` 단독 호출 금지** — 호출자 프로세스 cwd가 변이되어 형제 sub-agent의 hook 판정과 후속 도구 호출이 깨진다.

## 4. worktree 테스트는 worktree 소스를 import해야 한다 (검증 게이트 신뢰성)

- 테스트는 worktree 디렉토리에서 `uv run pytest`(또는 `mise run //<module>:test*`)로만 호출한다 — `uv run`이 cwd 기준으로 venv를 resolve하고 불일치 `VIRTUAL_ENV`를 무시하며, worktree venv 부재 시 그 시점에 생성·동기화한다.
- raw 인터프리터 경로(`<other-checkout>/.venv/bin/python -m pytest`)·`VIRTUAL_ENV` 존중 호출 금지 — 다른 체크아웃 소스를 import하여 거짓 통과(silent false-green)를 만든다.
- 런타임 가드(`tests/conftest.py` `pytest_configure`)가 import 패키지 경로의 pytest `rootpath` 하위 여부를 검사하여 위반 시 세션 즉시 중단 — abort 시 위 `uv run` 절차로 재실행한다.

## 5. 형제 격리는 컨벤션 의존이라는 한계

- hook(`.agents/hooks/check-worktree-isolation.sh`)의 강제 범위는 파일 쓰기 도구(`Edit`·`Write`·`MultiEdit`·`NotebookEdit`·`apply_patch`)와 shell 계열 도구(`exec_command`·`Bash`·`shell`·`unified_exec`)의 root checkout mutation 차단이다.
- sub-agent별 워크트리 소유를 식별할 채널은 없으므로 형제 워크트리 mutation은 컨벤션 의존이다.
- 형제 워크트리로의 파일 mutation·bare `cd` 단독 호출은 hook이 완전히 판별하지 못한다 — §1~§3 컨벤션이 최종 방지 수단이다.
