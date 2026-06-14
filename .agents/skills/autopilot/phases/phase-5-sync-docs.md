# Phase 5: 문서 동기화

별도 서브에이전트로 `/sync-docs`를 호출하여 프로젝트 문서/를 코드베이스 기준으로 갱신한다. `/sync-docs`가 전용 워크트리 생성→commit→push→PR→머지까지 자체 전달을 책임지고 `pr: URL`을 반환한다 (`sync-docs/phases/phase-5-deliver.md`).

```
Agent(
  subagent_type: "general-purpose",
  description: "sync-docs after milestone",
  permission_mode: "bypassPermissions",  # phase-3-wave-loop.md §3-2-ter 조건부 inherit
  prompt: "Invoke the /sync-docs skill. 본 autopilot 실행에서 머지된 PR [{PR_LIST}]의 변경이 프로젝트 문서/에 반영되도록 동기화하라. Verify 게이트를 통과한 내용만 반영. **반환 형식 (5줄 이내)**: `updated: N개` 다음 줄에 갱신 경로 / `pr: URL 또는 none`. 동기화 과정·diff 내용 반환 금지."
)
```

## 반환 처리 — PR URL 그대로 리포트 반영 (재작업 금지)

`/sync-docs`가 산출물 전달(워크트리·commit·PR·머지)을 책임지므로, 메인은 반환된 `pr: URL`을 **그대로 Phase 6 리포트에 반영**한다. 메인이 sync 산출물을 재작업하지 않는다 — 다음 분기를 수행하지 않는다:

- 공유 eng-docs 체크아웃 소유권 포렌식·dirty 정리
- eng-docs 워크트리 재생성·Writer Edit 재적용
- PR 재생성·머지 재실행

반환이 `pr: none`이면 동기화 대상이 없었다는 뜻이므로 그대로 리포트에 "프로젝트 문서 변경 없음"으로 반영한다. 반환이 미머지 PR URL(`pr: URL (미머지 — ...)`)이면 그 사실을 리포트에 노출한다 — 메인이 직접 머지를 떠맡지 않는다.
