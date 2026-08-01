# Phase 5: 문서 동기화

별도 서브에이전트로 `/sync-docs`를 호출하여 프로젝트 문서/를 코드베이스 기준으로 갱신한다. 이 phase의 독립 전달과 반환 계약은 `sync-docs/SKILL.md`의 `sync-docs-delivery-contract` 블록을 따른다.

```
Agent(
  subagent_type: "general-purpose",
  description: "sync-docs after milestone",
  permission_mode: "bypassPermissions",  # phase-3-wave-loop.md §3-2-ter 조건부 inherit
  prompt: "Invoke the /sync-docs skill with caller marker `delivery-mode: standalone`. 본 autopilot 실행에서 머지된 PR [{PR_LIST}]의 변경이 프로젝트 문서/에 반영되도록 동기화하라. Verify 게이트를 통과한 내용만 반영. **반환 형식 (5줄 이내)**: `updated: N개` 다음 줄에 갱신 경로 / `pr: <URL>` 또는 `pr: none` 또는 `pr: <URL> (미머지 — <사유>)`. 동기화 과정·diff 내용 반환 금지."
)
```

## 반환 처리 — PR URL 그대로 리포트 반영 (재작업 금지)

독립 전달 모드의 `/sync-docs`가 전달 계약 전체를 책임지므로, 메인은 반환된 `pr: URL`을 **그대로 Phase 6 리포트에 반영**한다. 메인이 sync 산출물을 재작업하지 않는다 — 다음 분기를 수행하지 않는다:

- 공유 eng-docs 체크아웃 소유권 포렌식·dirty 정리
- eng-docs 워크트리 재생성·Writer Edit 재적용
- PR 재생성·머지 재실행

반환이 `pr: none`이면 동기화 대상이 없었다는 뜻이므로 그대로 리포트에 "프로젝트 문서 변경 없음"으로 반영한다. 반환이 `pr: <URL> (미머지 — <사유>)`이면 URL과 사유를 리포트에 노출한다 — 메인이 직접 머지를 떠맡지 않는다.
