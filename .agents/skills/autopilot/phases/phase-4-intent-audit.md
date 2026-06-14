# Phase 4: 마일스톤 의도 감사

머지된 PR이 마일스톤/부모 이슈의 기획 의도(목적 어휘 — 제품·사용자·운영 관점의 가치)를 실제로 충족했는지 자가 감사한다. 메인 세션 컨텍스트 보호를 위해 **별도 서브에이전트**로 위임한다.

```
Agent(
  subagent_type: "general-purpose",
  description: "milestone intent audit",
  model: "sonnet",  # 의도↔PR 체크리스트 대조 작업 — opus 설계 추론 불요
  permission_mode: "bypassPermissions",  # phase-3-wave-loop.md §3-2-ter 조건부 inherit
  prompt: "마일스톤/부모 이슈 [{인자}]의 기획 의도와 본 autopilot 실행에서 머지된 PR 목록 [{PR_LIST}]을 대조하여, 기획 당시 의도한 가치가 코드베이스에 모두 반영되었는지 감사하라.
  - 마일스톤/부모 이슈 본문에서 목적 어휘(제품·사용자·운영 가치)를 추출
  - 머지된 PR description + diff 요약을 수집
  - **머지 반영 여부 판정의 권위 소스는 origin/develop 또는 PR diff다 — 로컬 워킹트리 grep 금지**: FR이 코드베이스에 반영되었는지 확인할 때 로컬 체크아웃 파일을 grep하지 말 것. 로컬 develop는 fetch만 되고 pull되지 않아 origin/develop보다 뒤처질 수 있어 거짓 음성(미반영 오판)을 낳는다. `git fetch origin develop` 후 `git show origin/develop:<path>` 또는 `gh pr diff <PR>`로 머지 반영본을 직접 읽어 판정한다.
  - 가치 항목별로 충족/부분 충족(gap)/미충족 판정
  - gap이 있으면 후속 이슈 후보(제목 + 1줄 근거)를 제시
  - charter §4-A 의도 정렬 위반(스펙↔코드 충돌, 도메인 사전 미등록 어휘 등)이 발견되면 critical로 표기
  **반환 형식 (15줄 이내, 산문 금지)**: `충족: N개` / `gap: M개` 다음 줄에 각 gap을 `- {제목}: {1줄 근거}` / `critical: K개` 다음 줄에 각 critical을 `- {1줄}`. 감사 과정·중간 추론 반환 금지."
)
```

감사 결과 분기:
- **충족**: Phase 5 진행.
- **gap만 있음**: Phase 5 진행. 즉시 후속 이슈 자동 생성 + 분해 시작 (`behavioral-guidelines.md` "스펙 검증 / 후속 이슈" SSOT "후속 이슈 자동 실행 default = 즉시 분해" 정합). 본 autopilot 세션 내에 background sub-agent로 `/process-ticket {신규-ISSUE-NUMBER}` spawn. 최종 리포트에 gap 목록 + 생성된 후속 이슈 번호를 포함한다.
- **critical 있음**: 즉시 stop. 사용자에게 critical 항목을 보고하고 질의. Phase 5 진행하지 않음.
