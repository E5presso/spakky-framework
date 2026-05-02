# Phase 2: DAG 구성 & 웨이브 계산

1. **부모 epic 의존 재작성 (Phase 1 epic 제외와 짝)**: Phase 1 §3에서 부모 epic을 대상 집합에서 제외했으므로, 그 epic을 `blockedBy`로 가진 자식 티켓의 의존은 단순 누락된다 — 이대로 DAG를 짜면 그 자식이 epic의 자식 티켓 묶음 머지를 기다리지 않고 조기 진입한다. 따라서 DAG 구성 전, 각 티켓 `T`의 `blockedBy`를 epic 전개로 재작성한다.

   **알고리즘**:
   ```
   def expand(B, target_milestone):
     # B가 부모 epic이면 자식들로 치환, 자식이 또 epic이면 재귀
     if B is parent_epic_in_target_milestone:
       result = []
       for C in B.children where C.milestone == target_milestone:
         result.extend(expand(C, target_milestone))
       return result
     else:
       return [B]

   for T in target_tickets:
     new_blocked_by = []
     for B in T.blockedBy:
       new_blocked_by.extend(expand(B, target_milestone))
     T.blockedBy = dedup(new_blocked_by)
   ```

   핵심 속성:
   1. 부모 epic은 전개 후 어떤 `blockedBy`에도 남지 않는다.
   2. 자식이 다시 부모 epic이면 재귀 전개 (다단 트리 지원).
   3. 동일 자식이 여러 epic을 통해 도달하면 dedup.
   4. 대상 마일스톤(또는 부모 이슈 / 이슈 목록 인자가 정의한 대상 집합) 밖 자식은 무시 — Phase 1 대상 집합 정의와 일관.
   5. epic 식별 기준은 Phase 1 §3과 동일 (자식 티켓 보유 + 자식 중 하나 이상이 대상 집합에 속함). 식별 결과를 Phase 1과 Phase 2가 공유한다.

2. **집합 내부 의존만 반영**:
   - §1 재작성 후 각 티켓의 `blockedBy`에서 **대상 집합에 속한** 티켓만 엣지로 추가.
   - 대상 집합 외부 의존은 "외부 blocker"로 경고 출력하되 무시(사전 완료 가정).
3. **순환 검사**: 위상정렬(Kahn) 실패 시 즉시 중단하고 사용자에게 순환 경로를 보고 (기술적 모순 = 질의 트리거).
4. **웨이브 계산**: DAG depth별로 `wave[0..k]` 생성. `wave[0]`은 진입 노드(블로커 없음).
5. **사용자 보고 (승인 게이트 없음)**:
   - 웨이브별 티켓 수 요약 테이블.
   - Mermaid `flowchart LR` 다이어그램(노드=티켓, 엣지=blockedBy).
   - 보고 직후 Phase 3 자동 진입.
