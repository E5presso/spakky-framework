# Phase 4.5: 수용 기준 자가 grep 게이트

`/review-code` 수렴 + 최종 `/check` 통과 직후, Phase 5(commit/push/PR) 진입 직전에 **이슈 본문의 "수용 기준" 섹션에 박힌 grep 라인을 워크트리에서 실제 실행**하여 모든 라인의 기대값 일치 여부를 검증한다. `/review-code`는 코드 품질만 검토하므로 본문 명세 항목 중 일부만 처리하고 나머지가 누락되어도 결함으로 보지 않는다 — 본 게이트는 본문 grep 라인의 기계적 실행으로 그 갭을 차단한다.

## 1. 수용 기준 grep 라인 추출

Phase 1에서 수집한 이슈 본문(`gh issue view <N> --json body`)에서 **"수용 기준" / "Acceptance Criteria" 섹션의 grep / find / rg / 코드 식별자 검증 라인**을 추출한다. 추출 대상:

- 코드 fence 안의 `grep ...`, `rg ...`, `find ...`, `ls ...` 명령 라인 (기대값 명시: "0 hits", "no match", "exit 1" 등).
- 본문이 명시한 식별자 부재/존재 검증 (예: "`coerce_legacy_*` 함수 0개", "`plugins/spakky-foo/src/legacy_adapter.py` 파일 없음").
- `0 hits` / `0 matches` / `not found` / `없음` 키워드와 결합된 라인.

추출 결과를 `acceptance_grep` 배열로 정리한다 (각 entry: `{ line, expected }`). 본문에 grep 라인이 1건도 없으면 `acceptance_check: missing`으로 분류하고 본 게이트는 통과 처리한다 (게이트 자체는 차단하지 않으나 반환 형식의 `acceptance_check` 필드로 가시화).

## 2. 워크트리에서 실제 실행

각 grep 라인을 워크트리 cwd에서 그대로 실행한다. 실행은 메인 컨텍스트의 Bash 도구로 직접 수행하며, 임의 명령 추가·라인 수정 금지 (본문에 박힌 그대로). 결과를 다음 분류로 판정:

| 기대값 | 판정 |
|--------|------|
| `0 hits` / `no match` / `not found` | exit non-zero 또는 stdout 빈 줄 → 일치 (PASS) |
| `0 hits` / `no match` / `not found` | exit 0 + stdout 비어 있지 않음 → 미충족 (FAIL) |
| `N hits` / 명시적 라인 매치 | stdout 라인 수 ≥ N → 일치 (PASS) |
| 명시적 부재 (`파일 없음`) | `ls`/`find` exit non-zero → 일치 (PASS) |

## 3. 분기

- **전 라인 일치 (PASS)**: `acceptance_check: PASS`로 기록하고 Phase 5 진입.
- **1건 이상 미충족 (FAIL)**: Phase 5 진입 차단. 미충족 라인 + 실제 출력을 구현 에이전트에게 다시 넘겨 추가 구현 + Phase 4.5 재실행. 동일 이슈에서 본 게이트가 2회 연속 미충족이면 charter §5 질의 트리거(스펙↔코드 직접 충돌)로 판단하여 `ask-delegate`로 메인에 위임 (sub-agent) / `AskUserQuestion` (사용자 직접 호출). 사용자가 "부분 머지 후 후속 처리"를 명시 선택하면 그 시점에 한해 `acceptance_check: partial` + Phase 5 진입이 허용된다 (정상 경로 아님 — 사용자 승인 예외).
- **본문에 grep 라인 없음 (missing)**: `acceptance_check: missing`으로 기록하고 Phase 5 진입. 본 케이스는 본문 자체에 외부 검증 가능한 기준이 없는 것이므로 본 게이트는 차단 책임이 없다. autopilot 외부 검증 routine은 본 케이스에서 PR diff vs 본문 명세 LLM 비교로 보강한다.

## 4. PR 본문 첨부 (외부 검증 가능 형태)

PASS 또는 partial 결과를 `/create-pr` 호출 시 PR 본문 "Acceptance Criteria" 섹션으로 전달한다. 형식:

```
## Acceptance Criteria (자가 grep)

- [x] `grep -r 'from .*plugins\.spakky_foo\.legacy_adapter' plugins/spakky-foo/src` → 0 hits (실제: 0)
- [x] `find plugins/spakky-foo/src -name 'coerce_legacy_*'` → 0 hits (실제: 0)
- [ ] `grep -r 'evaluator_graph_legacy' core/spakky/src` → 0 hits (실제: 3) ← 미충족
```

autopilot 메인은 PR 본문에서 본 섹션을 회수하여 외부 검증의 입력으로 사용한다.

## 5. 자기 보고 silent corruption 차단

본 게이트가 차단되지 않은 채 `acceptance_check: PASS` 보고가 나가면 autopilot은 자가 검증 통과로 간주하고 다음 wave로 진입한다. 따라서 **`acceptance_check` 필드는 실제 grep 실행 결과로만 채운다** — 추론·낙관적 추정 금지. grep 실행이 환경 의존(예: 도구 부재)으로 막히면 `acceptance_check: missing` + `notes: acceptance-grep-blocked: <원인>`으로 가시화하고 Phase 5 진입한다 (본 작업은 차단하지 않되 호출자가 회수).
