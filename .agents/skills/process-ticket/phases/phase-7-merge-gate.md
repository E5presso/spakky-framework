# Phase 7: 병합 준비 완료

> **Phase 진입 ping** (sub-agent 한정): merge-gate 진입 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 7 merge-gate | issue: <N> | awaiting merge` 또는 `... | auto-merging`). SKILL.md "Phase 전환 progress ping" SSOT.

> **`--overnight` 모드**: PR 상태(번호, URL, CI 결과, 대기 중인 타인 코멘트 목록)를 요약하여 **즉시 반환**한다. `AskUserQuestion`을 호출하지 않고, `gh pr merge`도 실행하지 않으며, Phase 8을 건너뛴다. 사용자는 아침에 autopilot 리포트를 보고 수동으로 머지한다.

> **`--auto-merge` 모드**: 사용자가 사전 승인한 것으로 간주. `AskUserQuestion`을 호출하지 않고 PR 상태(번호, URL, CI 결과, review bot HEAD 평가 완료)를 간단히 알린 뒤 즉시 Phase 8로 진행하여 squash merge를 수행한다. `--overnight`와 동시 지정 시 `--auto-merge`가 우선한다.

PR이 병합 가능 상태가 되면:

1. **포그라운드 채팅**으로 PR 상태를 알리고 병합 승인을 받는다 — sub-agent로 실행 중이면 SKILL.md "사용자 질의 위임" 절의 `ask-delegate`로 메인에 위임 (`phase: Phase 7`, `trigger: merge-approval`), 사용자 직접 호출이면 아래 `AskUserQuestion` 직접:
   ```yaml
   question: "PR #{PR_NUMBER} 병합 준비 완료 (CI 통과 + GitHub mergeable). 어떻게 할까요?"
   header: "병합"
   options:
     - label: "Squash merge (Recommended)"
       description: "커밋을 하나로 합쳐서 병합합니다"
     - label: "보류"
       description: "병합하지 않고 작업을 종료합니다"
     - label: "모니터링 계속"
       description: "Phase 6 모니터링 루프로 복귀합니다"
   ```
2. "보류" 선택 시 Phase 8을 건너뛰고 작업을 종료한다.
3. "모니터링 계속" 선택 시 Phase 6 모니터링 루프로 복귀한다.
