# Phase 5: 문서 동기화

별도 서브에이전트로 `sync-docs`를 호출하여 코드베이스 기준으로 문서를 갱신한다.

```
Agent(
  subagent_type: "general-purpose",
  description: "sync-docs after milestone",
  permission_mode: "bypassPermissions",  # phase-3-wave-loop.md §3-2-ter 조건부 inherit
  prompt: "Invoke the `sync-docs` skill. 본 autopilot 실행에서 머지된 PR [{PR_LIST}]의 변경이 패키지 README·docs·CONTRIBUTING.md·ARCHITECTURE.md에 반영되도록 동기화하라. Verify 게이트를 통과한 내용만 반영. **반환 형식 (5줄 이내)**: `updated: N개` 다음 줄에 갱신 경로 / `pr: URL 또는 none`. 동기화 과정·diff 내용 반환 금지."
)
```
