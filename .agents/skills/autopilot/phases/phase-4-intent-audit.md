# Phase 4: 마일스톤 의도 감사

머지된 PR이 마일스톤/부모 이슈의 기획 의도(목적 어휘 — 제품·사용자·운영 관점의 가치)를 실제로 충족했는지 자가 감사한다. 메인 세션 컨텍스트 보호를 위해 **별도 서브에이전트**로 위임한다.

```
Agent(
  subagent_type: "general-purpose",
  description: "milestone intent audit",
  permission_mode: "bypassPermissions",  # phase-3-wave-loop.md §3-2-ter 조건부 inherit
  prompt: "마일스톤/부모 이슈 [{인자}]의 기획 의도와 본 autopilot 실행에서 머지된 PR 목록 [{PR_LIST}]을 대조하여, 기획 당시 의도한 가치가 코드베이스에 모두 반영되었는지 감사하라.
  - 마일스톤/부모 이슈 본문에서 목적 어휘(제품·사용자·운영 가치)를 추출
  - 머지된 PR description + diff 요약을 수집
  - 가치 항목별로 충족/부분 충족(gap)/미충족 판정
  - gap이 있으면 후속 티켓 후보(제목 + 1줄 근거)를 제시
  - charter §4-A 의도 정렬 위반(스펙↔코드 충돌, 도메인 사전 미등록 어휘 등)이 발견되면 critical로 표기
  **반환 형식 (15줄 이내, 산문 금지)**: `충족: N개` / `gap: M개` 다음 줄에 각 gap을 `- {제목}: {1줄 근거}` / `critical: K개` 다음 줄에 각 critical을 `- {1줄}`. 감사 과정·중간 추론 반환 금지."
)
```

감사 결과 분기:
- **충족**: Phase 5 진행.
- **gap만 있음**: Phase 5 진행. 최종 리포트에 gap 목록 + 후속 티켓 후보를 포함하고, **사용자에게 후속 티켓 생성 여부를 질의**한다 (자동 생성 안 함 — charter §4-A 의도 정렬은 사용자 판정 필요).
- **critical 있음**: 즉시 stop. 사용자에게 critical 항목을 보고하고 질의. Phase 5 진행하지 않음.
