# ADR-0014: AI PR 리뷰 자동 승인 정책

- **상태**: Accepted
- **날짜**: 2026-06-26
- **대체**: 해당 없음
- **관련**: [ADR-0013](0013-declarative-agent-loop-ownership.md), GitHub Issues #448, #449, #450

## 맥락 (Context)

`develop` branch protection은 PR당 formal approval 1개를 요구한다. 하지만 현재 운영 흐름은 메인테이너 1인이 주로 PR을 작성하고 검토하므로, 같은 사용자가 자기 PR을 approve할 수 없다는 GitHub 정책 때문에 매 PR마다 사람 승인 대기 또는 admin merge가 필요했다.

이번 결정은 승인 요건을 제거하지 않는다. 대신 로컬 에이전트가 기존 결함 기준으로 exact-head verdict를 산출하고, 자동 승인 가능한 PR에 대해서만 GitHub Actions bot이 formal Approve를 남기게 한다. 품질 판단은 fresh PR review 또는 `/process-ticket`의 독립 committed-head review가 맡고, 신호 무결성은 receipt publisher, GitHub commit status, Actions workflow의 출처·권한 게이트가 맡는다.

현재 구현된 구성은 다음과 같다.

- `.agents/skills/pr-review/SKILL.md`는 기본 호출에서 열린 PR을 fresh review하고, 명시적 `--process-state` 호출에서는 `/process-ticket`이 만든 full exact-head PASS receipt만 게시한다.
- `.agents/skills/process-ticket/scripts/review_receipt.py`는 frozen criteria manifest와 C01–C14 receipt를 검증하며, `.agents/skills/pr-review/scripts/publish_final_review.py`는 live issue·PR·GitHub surface를 read-back해 publication을 수렴시킨다.
- `.github/workflows/ai-review.yml`은 `status` 이벤트에서 context가 `ai-review`, state가 `success`일 때만 실행된다.
- `.github/scripts/ai_review_auto_approve.sh`는 PR head SHA, 같은 repo 여부, 최신 `ai-review` status creator 권한, 기존 bot approval 중복 여부를 GitHub API로 재조회한 뒤 `github-actions[bot]` approval을 남긴다.

## 결정 동인 (Decision Drivers)

- 기존 branch protection의 "승인 1개" 요건을 유지하면서 반복적인 admin merge를 줄여야 한다.
- PR 코멘트와 라벨처럼 위조·오해 가능한 표면을 승인 트리거로 쓰지 않아야 한다.
- fork PR과 stale status가 자동 승인되는 경로를 차단해야 한다.
- status 생성자를 이벤트 `sender`가 아니라 commit status API의 `creator`로 재조회해야 한다.
- 메인테이너 login을 하드코딩하지 않고 GitHub collaborator role로 admin/maintain 권한을 판정해야 한다.
- 같은 exact-head 품질 판정을 `/process-ticket`의 final review와 PR 단계에서 중복 생성하지 않아야 한다.
- 리뷰 재사용은 C01–C14 14/14 독립 재검증과 criteria·issue·head digest를 보존하며 stale·BLOCK·불완전 증거를 fail-closed해야 한다.
- `ai-review`를 required status check로 강제하지 않아 사람 수동 승인 override와 기존 branch protection 의미를 보존해야 한다.
- secret key나 HMAC 서명은 GitHub 권한 모델이 이미 제공하는 인증을 중복하며, PR diff prompt injection 자체를 막지 못한다.

## 고려한 대안 (Considered Options)

### 대안 A: 기존 수동 승인 또는 admin merge 유지

메인테이너가 모든 PR을 직접 승인 가능한 외부 계정으로 처리하거나 admin merge로 우회한다.

장점:

- 추가 workflow가 필요 없다.
- GitHub native branch protection 설정을 건드리지 않는다.

단점:

- 마일스톤의 자동화 목적을 달성하지 못한다.
- 매 PR마다 사람이 승인 표면을 수동 처리해야 한다.
- admin merge가 반복되어 branch protection의 정상 경로를 우회하는 습관을 만든다.

### 대안 B: PR 코멘트 marker 또는 라벨을 승인 트리거로 사용

`/pr-review`가 남긴 verdict marker나 `auto-approvable` 라벨을 workflow가 읽고 승인한다.

장점:

- 사람이 PR 화면에서 상태를 이해하기 쉽다.
- 구현이 단순해 보인다.

단점:

- 코멘트와 라벨은 승인 신호로 쓰기에는 표면이 넓고 의미가 혼동된다.
- 라벨은 monitor-pr bot-stuck 복구 신호와 역할이 겹쳐 stale label 위험을 만든다.
- issue comment body를 신뢰 신호로 쓰면 PR 본문·diff·코멘트 injection과 구분하기 어렵다.

### 대안 C: verdict에 secret key 또는 HMAC 서명 도입

`/pr-review`가 verdict payload를 secret으로 서명하고 workflow가 서명을 검증한다.

장점:

- commit status 외의 payload 무결성을 별도 검증할 수 있다.

단점:

- 로컬 에이전트 실행 환경과 GitHub Actions 사이에 secret 배포·회전 문제가 생긴다.
- 서명은 "누가 payload를 만들었는가"만 보장하며, PR diff prompt injection이나 잘못된 verdict 자체를 막지 못한다.
- GitHub commit status 생성 권한과 collaborator permission gate가 이미 필요한 인증 경계를 제공한다.

### 대안 D: commit status 기반 verdict + GitHub 신뢰 데이터 게이트 (채택)

`/pr-review`는 verdict를 head commit의 `ai-review` status로 발행하고, Actions workflow는 status 이벤트만 승인 트리거로 삼는다. 승인 직전 workflow는 GitHub API로 열린 PR head SHA, 같은 repo 여부, 최신 `ai-review` status creator, creator role을 재조회한다.

장점:

- 승인 트리거가 write 권한이 필요한 commit status로 좁아진다.
- fork PR과 stale status를 GitHub 신뢰 데이터로 차단한다.
- admin/maintain 권한 판정이 login 하드코딩 없이 collaborator role에 묶인다.
- PR 코멘트와 라벨은 정보·복구 표면으로 남겨도 승인 신호와 분리된다.
- `ai-review`를 required check로 만들지 않아 사람 수동 승인 경로를 유지한다.

단점:

- repo 설정 "Allow GitHub Actions to create and approve pull requests"가 필요하다.
- status 이벤트에는 PR 번호가 없어서 commit SHA에서 열린 PR을 역해석하는 API 호출이 필요하다.
- workflow가 기본 브랜치에 들어가기 전까지는 자기 자신을 자동 승인할 수 없다.

## 결정 (Decision)

대안 D를 채택한다.

정책:

- 기본 `/pr-review <PR>`는 열린 PR diff를 기존 review SSOT로 fresh review하고 verdict를 하나만 낸다: `AUTO_APPROVE`, `CHANGES_REQUESTED`, `HUMAN_REVIEW`.
- `/process-ticket`은 commit 후 push 전에 runtime canonical `owner`·`implementer`와 다른 reviewer에게 clean committed HEAD의 C01–C14를 모두 재검증시켜 full `PASS` 또는 `BLOCK` receipt를 만든다. Process state의 `final_review_delegate`가 `{head_sha, criteria_digest, reviewer}` provenance를 보존하고, reviewer result의 동명 필드가 byte-for-byte 일치해야 한다. Phase 4 verdict와 reviewer가 제출한 임의 identity 문자열은 상속하지 않는다.
- `build-full`은 clean committed HEAD와 process state provenance를 검증하고, local remote ref와 configured upstream 또는 `origin`의 live heads를 bounded read-back해 현재 exact HEAD가 이미 push되었으면 거부한다. Blocker reproduction은 `{command, head_sha, exit_code, output_digest}` 구조이며 receipt HEAD와 재현 HEAD가 같아야 한다.
- `/pr-review <PR> --process-state <PATH>`는 full exact-head `PASS`, blocker 0, C01–C14 14/14 reverified·inherited 0 receipt만 게시한다. 이 모드는 명시적으로만 선택되며 receipt가 missing·malformed·stale·BLOCK·delta이면 GitHub mutation 전에 실패하고 fresh review로 fallback하지 않는다.
- Criteria manifest는 정책에 열거된 review source와 정규화한 live issue body를 digest한다. Delta receipt validator는 ancestor·동일 criteria·완전한 category split을 검사하지만 첫 rollout의 publication 증거로는 허용하지 않는다.
- verdict는 head commit의 `ai-review` status로 매핑된다: `AUTO_APPROVE=success`, `CHANGES_REQUESTED=failure`, `HUMAN_REVIEW=pending`.
- PR 코멘트의 verdict marker와 `auto-approvable` 라벨은 승인 트리거가 아니다. 코멘트는 사람이 읽는 요약이고, 라벨은 `monitor-pr` bot-stuck 복구 허용 신호다.
- Receipt publisher는 local HEAD, commit, push, upstream, 저장된 PR, live PR head와 live issue digest를 preflight에서 일치시킨다. 통과 후 exact receipt body와 creator role `admin|maintain`을 모두 만족하는 canonical comment를 read-back하고 label을 확인하며, issue·PR commit-point를 다시 검증한 뒤 trusted `ai-review=success` status를 마지막에 게시한다. 재실행은 전체 pagination의 immutable ID를 기준으로 기존 surface를 재사용하고 누락된 surface만 복구한다.
- Autopilot resume은 `pr_opened`가 있으면 stored `publication.state`가 `pending`·`incomplete`·`published` 중 무엇이든 monitor·merge보다 explicit process-state publisher를 먼저 재실행한다. Stored state는 힌트일 뿐이며, 이번 실행의 live comment·label·status read-back이 `published`를 다시 기록한 경우에만 monitor를 재개한다. Publisher 실패를 manual fresh review로 우회하지 않는다.
- `.github/workflows/ai-review.yml`은 `status` 이벤트만 사용하고, context가 `ai-review`이며 state가 `success`일 때만 승인 후보로 본다.
- workflow는 승인 직전에 다음을 모두 재확인한다.
  - commit SHA가 열린 PR의 current head SHA다.
  - PR `head.repo.full_name`이 `base.repo.full_name`과 같다.
  - 최신 `ai-review` status의 `creator.login`이 존재한다.
  - creator의 collaborator `role_name`이 `admin` 또는 `maintain`이다.
  - 같은 SHA에 대한 `github-actions[bot]` approval이 이미 있으면 중복 승인하지 않는다.
- repo 설정 `can_approve_pull_request_reviews`는 활성 상태여야 한다. 비활성 상태에서 approval이 422로 실패하면 workflow 실패로 드러나야 하며 silent fallback하지 않는다.
- `ai-review`는 `develop`의 required status check로 강제하지 않는다. 이 신호는 기존 branch protection의 formal approval 요건을 충족시키는 자동 승인 배관이며, 필요하면 사람 수동 승인으로도 PR을 진행할 수 있다.

## 결과 (Consequences)

### 긍정적

- 메인테이너 본인 PR도 검증된 `ai-review=success` status를 통해 bot approval을 받을 수 있다.
- 반복적인 admin merge 필요가 줄어든다.
- `/process-ticket`은 같은 exact-head를 PR 단계에서 다시 review하지 않고도 독립 C01–C14 품질 증거를 게시할 수 있다.
- Runtime identity와 delegate/result 결속이 구현자의 임의 reviewer 선언 또는 다른 HEAD·criteria 결과 재사용을 차단한다.
- 승인 트리거가 commit status로 제한되고, fork/stale/권한미달 경로가 GitHub API 재조회로 차단된다.
- `/review-code`는 결함 의문점 생성 스킬, `/pr-review`는 PR verdict와 승인 신호 발행 스킬로 역할이 분리된다.

### 부정적

- 수동 PR은 push 후 `/pr-review <PR_NUMBER>` fresh review가 필요하고, `/process-ticket`은 push 전 full review와 push 후 명시적 `--process-state` publication을 모두 완료해야 한다.
- Receipt publication은 clean exact-head와 live GitHub read-back을 요구하므로 partial failure가 발생하면 `incomplete` 상태에서 같은 명령으로 복구해야 한다.
- workflow가 기본 브랜치에 없거나 repo Actions 승인 설정이 꺼져 있으면 봇 approval이 생성되지 않는다.
- `ai-review=success`가 품질 보증의 전부가 아니며, review SSOT와 branch protection이 계속 함께 작동해야 한다.

### 중립적

- branch protection의 approval count는 유지된다.
- `ai-review`는 required status check가 아니다.
- secret key/HMAC 기반 verdict 서명은 도입하지 않는다.
- fork PR은 자동 승인 대상이 아니며 사람 검토로 남는다.

## 검증 기준

- 결함 없는 같은 repo PR에서 기본 `/pr-review`의 `AUTO_APPROVE` 또는 explicit process-state publisher의 full exact-head PASS가 trusted `ai-review=success`를 게시하면 workflow가 `github-actions[bot]` approval을 남긴다.
- Missing·malformed·stale·BLOCK·delta receipt, dirty worktree, head·issue·PR 불일치에서는 receipt publisher가 status를 게시하지 않는다.
- Owner·implementer·final reviewer provenance 불일치, reviewer result의 head·criteria·reviewer 불일치, malformed blocker reproduction, push 후 `build-full` 실행은 receipt 생성 또는 publication 전에 실패한다.
- Partial publication 재실행은 trusted creator의 exact-body canonical comment·label·trusted success를 재사용하고 누락분만 복구한다. Stored `publication.state=published`도 live surface drift를 숨기는 권위가 아니며, publisher가 live read-back을 다시 마친 뒤에만 autopilot이 monitor·merge로 전이한다.
- Full receipt는 exact committed HEAD뿐 아니라 `origin/develop` merge-base와 `git diff --binary --no-ext-diff --no-textconv <base>...<head>` bytes의 SHA-256을 보존한다. `final_review_inputs`는 matching PASS/BLOCK receipt/result를 재검증하는 `cleanup-inputs`가 state key를 먼저 원자적으로 소비한 뒤 canonical temp 파일만 삭제한다.
- fork PR, stale status, admin/maintain 미만 creator, 코멘트 marker 또는 라벨만 있는 PR에서는 bot approval이 없다.
- 새 commit push 후에는 GitHub native stale-review dismissal이 기존 bot approval을 무효화하고, 새 head SHA에 대해 `/pr-review`를 다시 실행해야 한다.
- `develop` branch protection required status checks에 `ai-review`를 추가하지 않는다.

## 참고 자료

- `.agents/skills/pr-review/SKILL.md`
- `.agents/review-criteria-policy.json`
- `.agents/skills/process-ticket/scripts/review_receipt.py`
- `.agents/skills/pr-review/scripts/publish_final_review.py`
- `.agents/skills/autopilot/phases/phase-3-wave-loop.md`
- `.github/workflows/ai-review.yml`
- `.github/scripts/ai_review_auto_approve.sh`
- `.agents/skills/monitor-pr/SKILL.md`
