---
name: review-pr
description: PR 리뷰 코멘트를 트리아지하여 수용/반론을 판단하고, 수정 적용 후 스레드에 근거를 남깁니다
argument-hint: "[PR 번호]"
user-invocable: false
---

# PR 리뷰 코멘트 트리아지 & 반영

## Step 1: 코멘트 수집

1. PR 번호를 인자로 받거나, 현재 브랜치의 PR을 자동 탐지한다.
2. `gh api repos/{owner}/{repo}/pulls/{number}/comments`로 인라인 코멘트를 수집한다.
3. `gh pr view {number} --comments`로 일반 코멘트를 수집한다.
4. 봇 자동 코멘트(Codecov 등)는 제외하고, 리뷰어 코멘트만 대상으로 한다.

## Step 1.5: 이슈 스코프 파악

PR에 연결된 이슈 번호(`Closes #N`)를 추출하고, 이슈의 **목표, 수용 기준, 제약 사항**을 가져온다.
```bash
gh issue view {이슈번호} --json body -q .body
```
이 정보는 Step 2의 질문 #3(스코프 판단)에서 사용한다.

## Step 2: 코멘트별 판단 루프

각 코멘트에 대해 다음을 순서대로 수행한다.

### 2-1. 지적 이해

- 코멘트가 가리키는 코드를 **직접 읽는다**.
- 지적의 핵심을 한 문장으로 요약한다.

### 2-2. 타당성 검증

다음 질문을 순서대로 확인한다. **하나라도 No이면 반론**, 모두 Yes이면 수용.

| # | 질문 | No이면 |
|---|------|--------|
| 1 | 지적이 사실에 기반하는가? (코드를 잘못 읽거나, 실제로 발생하지 않는 문제를 지적한 건 아닌가) | 반론: 사실 오류 지적 |
| 2 | 제안된 변경이 문제를 실제로 해결하는가? | 반론: 근본 원인 불일치 |
| 3 | 변경의 범위가 현재 이슈 스코프 안에 있는가? (Step 1.5에서 파악한 목표/수용 기준/제약 사항과 대조) | 반론: 스코프 초과 → 별도 이슈 |
| 4 | 변경 후 더 나은 상태가 되는가? | 수용 |

**질문 #1 검증 필수**: 린트 경고를 지적하면 `uv run ruff check`로 실제 발생 여부를 확인한다. 타입 에러를 지적하면 `uv run pyrefly check`로 확인한다. 추측으로 수용하지 않는다.

### 2-3. 판단 결과 분류

| 분류 | 조건 |
|------|------|
| **수용** | 질문 1~4 모두 Yes |
| **반론** | 질문 중 하나 이상 No — 근거 명확 |
| **보류** | 판단 불가 — 사용자 확인 필요 |

## Step 3: 사용자에게 보고

코드 수정 **전에** 판단 결과를 보고하고 승인을 받는다.

```markdown
## 리뷰 코멘트 트리아지 결과

### 수용 (N건)
- [파일:라인] 요약 — 수용 이유 (판단 루프 #4: 근거)

### 반론 (N건)
- [파일:라인] 요약 — 반론 근거 (판단 루프 #N: 이유)

### 보류 (N건)
- [파일:라인] 요약 — 판단 불가 사유
```

## Step 4: 승인 후 실행

### 수용 건

1. 코드를 수정한다.
2. 수정 후 검증:
   - `uv run ruff check .` (해당 패키지 디렉토리 내에서)
   - `uv run pyrefly check` (해당 패키지 디렉토리 내에서)
   - `uv run pytest` (관련 테스트)
3. 기존 에러 무시, 내 변경으로 인한 새 에러만 수정한다.

### 반론 건

1. 코드를 수정하지 **않는다**.

### PR 스레드 응답 + resolve

수용/반론 모두 해당 코멘트 스레드에 답변한다. 응답은 GraphQL `addPullRequestReviewThreadReply` mutation 사용:

```bash
gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input: { pullRequestReviewThreadId: "<THREAD_ID>", body: "<응답>" }) { comment { id } } }'
```

- **수용**: "수용합니다. [한 줄 이유]"
- **반론**: "검토 결과 현행 유지로 판단했습니다. 근거: [판단 루프 #N 결과]" + 대안 제시
- 감정적 표현 금지. 근거와 사실만 기술한다.

### 스레드 resolve 권한 분리

응답을 단 직후, **스레드의 첫 코멘트 작성자(`author.__typename`)를 확인**하여 resolve 여부를 결정한다:

| 첫 코멘트 작성자 | 처리 |
|---|---|
| `Bot` (Copilot, Claude, Gemini 등) | `resolveReviewThread` mutation 으로 resolve. 봇은 재판정 프로세스가 없으므로 수정/응답 후 에이전트 resolve 로 충분 |
| `User` (사람 리뷰어) | **resolve 하지 않는다.** 응답만 달고 리뷰어 본인에게 판단 권한을 양도. 에이전트가 강제 resolve 하면 사회적 계약을 깬다 |

```bash
# Bot 스레드만 resolve
gh api graphql -f query='mutation { resolveReviewThread(input: { threadId: "<THREAD_ID>" }) { thread { isResolved } } }'
```

혼합 스레드(첫 코멘트 Bot, 이후 User 답변 존재 등)에서도 **첫 코멘트 작성자 기준**으로만 판단한다.

## 규칙

- 맹목적 수용 금지 — 모든 지적에 판단 루프를 실행한다.
- 맹목적 무시 금지 — No 판단에는 반드시 검증된 근거가 있어야 한다.
- 코드 수정 전에 반드시 사용자 승인을 받는다.
- PR 스레드에 판단 과정을 투명하게 남긴다.
