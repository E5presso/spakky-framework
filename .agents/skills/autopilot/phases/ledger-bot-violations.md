# §3-3-ter. 외부 봇 위반 카테고리 누적 (durable ledger)

> **로드 트리거**: Phase 3 wave 내 PR 머지 이벤트 발생 시 Read (`phase-3-wave-loop.md` §3-3-ter). 누적 결과는 `phase-3_6-meta-detection.md` §3.6-1 S6 시그널의 입력.

자가 검토(`/review-code`)·pre-commit 게이트를 통과한 PR이 외부 봇에서 위반을 받는 것은 로컬 게이트의 구조적 갭이며, 같은 카테고리의 임계 반복은 우연이 아닌 패턴이다.

## Ledger SSOT (단일 진입점)

- **경로**: `$CODEX_HOME/projects/-Users-spakky-Documents-projects-spakky-framework/state/bot-violation-ledger.json` (`CODEX_HOME` 미설정 시 `~/.codex`) — 세션 종료 후에도 유지되는 durable 위치. 본 path 외 분기 누적 금지 — 메모리·워크트리 state·세션 한정 임시 파일은 세션 종료 시 소실되어 약속 유기와 동등 (`behavioral-guidelines.md` "휘발성 스케줄러 절대 금지" 정합).
- **누적 진입점**: 본 § 1곳 — `monitor-pr` LISTENING 루프·`triage-comments`·다른 phase에서 누적 금지 (중복 카운트 방지).
- **스키마** (배열의 각 entry):

```json
{
  "label": "<짧은 카테고리명, 한국어 우선>",
  "count": 3,
  "evidence": [
    { "pr": "<PR URL>", "comment_id": <id>, "issue": "<ISSUE-NUMBER>" }
  ],
  "fired_issue": "<ISSUE-NUMBER 또는 null>",
  "fired_at": "<ISO-8601 timestamp 또는 null>"
}
```

`fired_issue`이 null이면 미spawn, 비어있지 않으면 spawn 상태 (중복 spawn 가드).

## 누적 절차 (PR 머지 직후 1회, 메인 직접 수행)

`wave_results[T].status == merged`인 각 이슈 `T`에 대해:

1. **봇 코멘트 수집**: `gh api repos/E5presso/spakky-framework/pulls/<PR>/reviews` + `pulls/<PR>/comments` + `issues/<PR>/comments` 전체 수집, `user.login`이 봇 계정(`[bot]` 접미)인 항목만 필터. 본인 reply 마커(`<!-- claude-agent-reply to=<id> -->`) 포함 항목은 자기 응답이므로 제외.
2. **위반 추출**: 각 봇 코멘트의 위반 여부를 LLM으로 판정 — 단순 정보·승인·LGTM 류 제외. 위반 1건당 (핵심 1줄 요약, 코멘트 id, PR URL, issue id) 튜플.
3. **카테고리 정규화 (LLM)**: 위반 요약을 짧은 한국어 카테고리 라벨로 정규화 — ledger의 기존 라벨 목록을 입력에 동봉하여 동의어가 같은 라벨로 합쳐지게 한다. 라벨 어휘 사전 고정 금지 — 일관된 짧은 명사구 생성.
4. **ledger 갱신**: 매치 라벨 존재 → `count += 1` + `evidence` append / 부재 → 신규 entry(`count = 1`, `fired_issue = null`). `fired_issue != null`인 entry는 별도 entry(라벨 ` (v2)` suffix)로 신규 누적 — fix 머지 후 회귀를 추적 가능하게 유지.
5. **atomic write**: 임시 파일에 쓴 뒤 `mv`. 디렉토리 부재 시 `mkdir -p`, 파일 부재 시 빈 배열(`[]`) 초기화. 동시 세션 race는 메인 단일 진입(§3.6-3) 강제로 부재.
