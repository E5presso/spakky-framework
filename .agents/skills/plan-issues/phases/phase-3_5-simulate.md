# Phase 3.5: 스펙 시뮬레이션 게이트 (Block Gate)

Phase 3 분해 artifact가 확정된 직후, **Phase 4 이슈 생성 전에 서브에이전트로 가벼운 시뮬레이션**을 돌려 스펙·DAG (Directed Acyclic Graph)·SC (Success Criteria)의 결함을 사전 검출한다.

## 본 단계의 의도

§11 self-review는 자기 판정이라 charter §4 외부 게이트의 self-confirmation bias 차단을 못 막는다. **외부 게이트 = 다른 컨텍스트로 같은 산출물을 읽고 결함을 보고**한다. `/plan-issues`가 만든 본문이 `/process-ticket`에게 어떻게 보이는지 사전 시뮬레이션한다.

4개 tier로 분리하여 비용을 최소화한다:

| Tier | 무엇 | 호출 횟수 | 적용 규모 |
|------|------|----------|-----------|
| **T1: Spec Probe** | 티켓 본문만으로 구현 가능한가, 모호함은 무엇인가 | 티켓 1건당 1회 | 모든 규모 |
| **T2: DAG (Directed Acyclic Graph) Coherence** | 후행 티켓이 선행 티켓의 약속하지 않은 산출물에 의존하는가 | 1회 (전체) | 에픽·그룹 |
| **T3: Value Drift** | SC (Success Criteria) 매핑이 표면적인지, 실제 산출물 합으로 SC 도달 가능한지 | 1회 (전체) | 에픽 |
| **T4: Grill-me Interview Replay** | 남은 질문 없이 진행 가능한지, 질문 순서·권장 답안·branch closure가 타당했는가 | 1회 (전체) | 자명 티켓 외 모든 규모 |

## 자명 티켓 — 시뮬레이션 생략 조건

Phase 2.5 스펙 승인 + Phase 3 분해 승인이 **모두** 생략된 자명 티켓(단일 + 단일 패키지 + 직접 도출 + 마커 0개 + 단일 태스크)은 Phase 3.5도 생략한다 — 이미 §11 self-review로 검증된 단일 명제는 시뮬레이션 비용이 정당화되지 않는다.

그 외 모든 규모는 본 단계를 수행한다.

---

## T1: Spec Probe (per-ticket)

각 태스크 draft를 **process-ticket이 실제로 보는 컨텍스트와 동일한 입력**으로 sub-agent에 전달하여 cold reading 시뮬레이션한다.

### 시뮬레이션 입력 정의

`/process-ticket`은 Phase 1 분석에서 다음 GitHub 컨텍스트를 명시적으로 조회한다 — 시뮬레이션도 동일 입력을 가진다:

| 입력 | 출처 | 비고 |
|------|------|------|
| 대상 티켓 본문 | Phase 3-8 draft | 시뮬레이션 대상 |
| 부모 이슈 본문 | Phase 3 draft (Sub-issue 위계의 부모) | 그룹 자식 태스크에 한함 |
| 마일스톤 description | Phase 2.5 공용 스펙 (에픽) | 에픽 자식 태스크에 한함 |
| Blocker 티켓 본문 | Phase 3-8 drafts (`blockedBy` GraphQL 관계) | 모두, 본문 전체 |
| 참조(related) 본문 | Phase 3 draft에 명시되었으면 | 본문에 언급된 경우만 |

**제외 대상** (cold session에서 못 보는 것): 이번 plan-issues 세션의 사용자 논의·합의·근거·미저장 메모. 이것이 "cold"의 핵심 — 본문에 적히지 않은 사용자 의도는 process-ticket 입장에서 fetch 불가능하므로, 본 시뮬레이션도 동일하게 배제한다.

### 호출 방식

태스크별로 1회씩 `Agent` 호출. **subagent_type=Explore** (read-only, codebase 접근 가능 — sub-agent가 "참조할 패턴"을 실제로 찾을 수 있는지도 검증).

병렬 실행: 모든 T1 호출을 한 메시지에 묶어 동시 발행 (호출 N개 = 1 round-trip의 wall-clock).

### Prompt 템플릿

```
당신은 새 세션의 코딩 에이전트(`/process-ticket`)입니다.
아래는 process-ticket이 Phase 1에서 fetch하는 GitHub Issue 컨텍스트와 동일한 입력입니다.
이 입력 + 코드베이스 탐색으로만 구현해야 합니다 — 이번 plan-issues 세션의
논의·사용자 의도는 fetch할 수 없습니다.

=== 마일스톤 description (에픽 자식 티켓인 경우) ===
{마일스톤 description 전체, 없으면 "해당 없음"}

=== 부모 이슈 본문 (그룹 자식인 경우) ===
{부모 이슈 본문 전체, 없으면 "해당 없음"}

=== Blocker 티켓 본문들 (있는 경우) ===
{각 blocker draft 본문을 임시 ID와 함께 전체 나열, 없으면 "해당 없음"}

=== 참조(related) 티켓 본문들 (본문에 언급된 경우) ===
{참조 티켓 본문, 없으면 "해당 없음"}

=== Decision Branch Ledger 요약 ===
{Phase 0~3에서 닫은 branch와 남은 branch. 없으면 "해당 없음"}

=== 대상 이슈 본문 (시뮬레이션 대상) ===
{태스크 draft 본문 전체}

질문 1: 위 컨텍스트만으로 구현을 시작하려면 어떤 정보가 부족합니까?
- "도메인 스펙"의 어떤 부분이 모호하거나 추론 없이 결정 불가입니까?
- "수용 기준"의 Given/When/Then 시나리오가 검증 가능한 단일 명제입니까, 아니면 추론으로 구체화해야 합니까?
- "참고 컨텍스트"의 탐색 지시어로 실제 코드 위치가 식별 가능합니까? (필요 시 코드베이스를 직접 탐색하여 확인)

질문 2: 위 컨텍스트에 명시되지 않았지만 구현 시 반드시 결정해야 하는 사항(silent assumption 후보)을 나열하세요. 마일스톤·부모·blocker 본문에서 추론 가능한 항목은 silent assumption 아님.

질문 3: 1-2 단락의 짧은 "내가 만들 것" 진술서를 작성하세요. 위 컨텍스트에 적힌 단어만 사용해야 합니다 — 컨텍스트에 없는 어휘를 사용하면 그 어휘 자체가 silent assumption입니다.

질문 4 (산출물 중복): "내가 만들 것" 진술서가 가리키는 산출물(파일·공개 함수·클래스·이벤트·매퍼 이름)이 코드베이스에 이미 존재하는지 직접 `Grep`으로 확인하세요. hit인 정의가 있으면 정의 위치(파일:라인)와 함께 보고하세요 — 본 단계는 Phase 1 산출물 중복 검사의 보강 게이트입니다.

질문 5 (branch closure): Decision Branch Ledger에서 이 티켓에 영향을 주는 branch가 본문에 반영되어 있습니까? ledger에는 닫혔지만 본문에는 없는 결정, 또는 본문에는 등장하지만 ledger/스펙에 없는 결정이 있으면 보고하세요.

답변 형식 (다른 글 금지):
AMBIGUITIES: ["{모호 항목 1줄}", ...]
ASSUMPTIONS: ["{silent assumption 후보 1줄}", ...]
WHAT_I_WILL_BUILD: "{1-2단락 진술서}"
EXISTING_ASSET_HITS: [{"name": "{명사구}", "location": "{파일:라인 또는 'none'}"}, ...]
BRANCH_DRIFT: ["{ledger와 본문 사이 불일치 1줄}", ...]
CONFIDENCE: HIGH | MEDIUM | LOW
```

### 출력 해석

- `AMBIGUITIES` 비어 있으면 → T1 통과 후보 (T2/T3에서 다시 검증)
- `AMBIGUITIES` 1개 이상 → "검토 후보 리스트"에 추가 (Soft block)
- `CONFIDENCE = LOW` → 자동 검토 후보 (AMBIGUITIES 비어 있어도)
- `WHAT_I_WILL_BUILD`에 컨텍스트(본문 + 마일스톤 + 부모 + blocker + related)에 없는 핵심 어휘가 등장 → 어휘 silent assumption으로 검토 후보
- `EXISTING_ASSET_HITS`의 `location`이 `none`이 아닌 항목이 1개 이상 → 산출물 중복 후보. Phase 1 산출물 중복 검사가 놓친 case이므로 검토 후보 리스트에 (출처 T1 산출물 중복) 별도 표시.
- `BRANCH_DRIFT` 1개 이상 → Phase 2.5 스펙 또는 Phase 3 draft가 ledger 결정을 누락한 것이므로 검토 후보 리스트에 추가.

### 비용 가이드

컨텍스트 확장으로 입력이 늘어난다. 티켓 수·마일스톤/부모/blocker 포함 여부를 기준으로 sub-agent 비용 추정치를 결과 보고 상단에 출력한다. 가격/모델 단가는 하드코딩하지 않는다.

---

## T2: DAG (Directed Acyclic Graph) Coherence (epic + group)

전체 티켓 본문 + DAG (Directed Acyclic Graph) + (에픽이면) 마일스톤 description을 한 번에 입력하여 **선후 관계 모순**을 검출한다.

### 호출 방식

`Agent` 1회. **subagent_type=general-purpose** (DAG (Directed Acyclic Graph)와 텍스트 동시 처리, 참조 도구 활용).

### Prompt 템플릿

```
다음은 plan-issues 스킬이 분해한 태스크 묶음과 의존성 그래프입니다.

=== 마일스톤 description (있는 경우) ===
{마일스톤 description 전체}

=== 태스크 본문 모음 ===
{T1 ID T1·T2·... 순으로 본문 전체 나열}

=== 의존성 표 ===
{Phase 3-3 충돌 매트릭스 + Phase 3-4/3-5 blockedBy 그래프}

=== FR 커버리지 표 ===
{Phase 3-6.5 FR 커버리지 표}

질문 1 (DAG 모순): 후행 티켓의 본문이 선행 티켓이 명시적으로 약속한 산출물(Port·DTO·이벤트·새 모듈) 외의 것을 가정합니까? 가정한다면 선행 티켓 어디에도 해당 산출물이 없는 것은 맞습니까? 모순 사례를 모두 나열하세요.

질문 2 (대표 태스크 적합성): 부모 경계 교차 blockedBy가 "결과 확정 대표 태스크"를 가리킨다고 선언되어 있습니다. 실제 대표 태스크 본문이 후행 티켓이 의존하는 산출물을 만드는지 확인하세요. 불일치를 나열하세요.

질문 3 (DAG 누락): 본문 분석 결과 발견된 implicit 의존(예: 티켓 B의 acceptance scenario가 티켓 A의 결과를 전제하는데 blockedBy로 선언 안 됨)을 나열하세요.

답변 형식 (다른 글 금지):
DAG_PARADOXES: [{"from": "T-N", "to": "T-M", "issue": "{한 줄 설명}"}, ...]
REPRESENTATIVE_MISMATCHES: [{"task": "T-N", "issue": "{한 줄}"}, ...]
MISSING_BLOCKERS: [{"from": "T-N", "to": "T-M", "reason": "{한 줄}"}, ...]
CONFIDENCE: HIGH | MEDIUM | LOW
```

### 비용 가이드

티켓 본문 전체 + DAG (Directed Acyclic Graph) + 마일스톤 입력을 기준으로 비용 추정치를 보고한다. 가격/모델 단가는 하드코딩하지 않는다.

---

## T3: Value Drift (epic only)

마일스톤 §10 SC (Success Criteria)와 자식 티켓 산출물 합 사이의 도달 가능성을 검증.

### 호출 방식

`Agent` 1회. **subagent_type=general-purpose**.

### Prompt 템플릿

```
다음은 마일스톤 단위 SDD 스펙과 자식 티켓 묶음입니다.

=== 마일스톤 §1 비즈니스 의도 ===
{본문}

=== 마일스톤 §10 성공 기준 (SC) ===
{본문}

=== SC 커버리지 표 ===
{Phase 3-6.5 SC 커버리지 표}

=== 자식 티켓 본문 모음 ===
{각 티켓의 "목표" + "사용자 시나리오" + "수용 기준"만 발췌, 도메인 스펙 섹션은 생략}

질문 1 (SC 도달 가능성): 각 SC에 대해, 매핑된 자식 티켓이 모두 완료되었을 때 (관찰 시점, 관찰 대상, 기대값) 3요소가 실제로 충족됩니까? 검증 절차를 1-2줄로 재진술하세요.

질문 2 (SC 표면 매핑): "기여 SC"로 선언되었지만 실제 본문 acceptance scenario가 SC를 직접 검증하지 않는 사례를 나열하세요.

질문 3 (Value Drift): §1 비즈니스 의도가 약속한 사용자/운영 변화 중, 어떤 SC도 검증하지 못하는 부분이 있는지 나열하세요.

답변 형식 (다른 글 금지):
UNREACHABLE_SC: [{"sc": "SC-NNN", "issue": "{한 줄}"}, ...]
SUPERFICIAL_MAPPINGS: [{"sc": "SC-NNN", "task": "T-N", "issue": "{한 줄}"}, ...]
INTENT_GAPS: ["{§1에 약속되었지만 SC로 검증되지 않는 변화}", ...]
CONFIDENCE: HIGH | MEDIUM | LOW
```

### 비용 가이드

마일스톤 의도와 SC (Success Criteria) 매핑 입력을 기준으로 비용 추정치를 보고한다. 가격/모델 단가는 하드코딩하지 않는다.

---

## T4: Grill-me Interview Replay (non-trivial)

Phase 0~3의 질문·응답·Decision Branch Ledger를 한 번 더 읽혀, **질문이 충분히 집요했는지와 질문 순서가 dependency-aware였는지**를 검증한다. T1은 티켓 본문 관점, T4는 계획 인터뷰 관점이다.

### 호출 방식

`Agent` 1회. **subagent_type=general-purpose**.

### Prompt 템플릿

```
다음은 plan-issues가 기능 방향성을 GitHub 이슈로 분해하기 전에 수행한 계획 인터뷰 기록입니다.
목표는 사용자를 더 괴롭히는 것이 아니라, 구현 시작 전에 닫아야 할 의사결정 가지가 남아 있는지 확인하는 것입니다.

=== 사용자 원문 ===
{초기 요청}

=== 질문/답변 기록 ===
{Phase 0~3에서 실제로 묻고 답한 질문. 질문마다 Q-ID, 권장 답안, 사용자 선택, 근거, 재질문 여부 포함}

=== Open Question Queue 기록 ===
{open_questions, answered_questions, deferred_by_evidence. 각 deferred 항목은 코드·문서·기존 이슈 근거 포함}

=== Decision Branch Ledger ===
{최종 ledger 전체}

=== Phase 2.5 스펙 요약 ===
{§1, §2, §5~§10 요약}

=== Phase 3 분해 요약 ===
{태스크 목록, 담당 FR/SC, blockedBy}

질문 1 (missing branch): architecture / domain model / API contract / data flow / UX-CLI surface / error policy / compatibility / rollout / tests-docs 중 구현 전 반드시 닫혀야 하지만 OPEN으로 남지 않았고 스펙에도 없는 branch가 있습니까?

질문 2 (bad question order): 후행 결정을 먼저 묻고 upstream 결정을 나중에 묻는 등 질문 순서가 dependency를 거슬러 사용자 답변을 왜곡한 지점이 있습니까?

질문 3 (unsupported recommendation): 권장 답안이 코드·문서·기존 이슈 근거 없이 제시되었거나, 사용자가 승인하지 않았는데 스펙에 반영된 사례가 있습니까?

질문 4 (over-questioning): 코드베이스 탐색으로 답할 수 있었는데 사용자에게 물은 질문이 있습니까? 있으면 코드 탐색으로 대체 가능한 근거를 제시하세요.

질문 5 (under-questioning): non-trivial 그룹/에픽인데 Mandatory Epic Grill Gate 또는 open question queue 없이 Phase 2.5로 진입한 흔적이 있습니까? 있다면 어떤 branch가 사용자 판단 없이 닫혔는지 나열하세요.

질문 6 (vague-answer closure): 사용자 답변이 추상적이었는데 같은 Q-ID로 재질문하지 않고 닫은 사례가 있습니까? 있다면 해당 Q-ID와 닫으면 안 되는 이유를 나열하세요.

답변 형식 (다른 글 금지):
MISSING_BRANCHES: [{"branch": "{branch}", "issue": "{한 줄}", "blocks": "{FR/SC/태스크}"}]
BAD_ORDER: [{"question": "{질문 식별자}", "issue": "{한 줄}"}]
UNSUPPORTED_RECOMMENDATIONS: [{"question": "{질문 식별자}", "issue": "{한 줄}"}]
OVER_QUESTIONING: [{"question": "{질문 식별자}", "code_or_doc_source": "{경로/이슈/문서 근거}"}]
UNDER_QUESTIONING: [{"branch": "{branch}", "issue": "{한 줄}", "should_have_asked": "{Q-ID 후보}"}]
VAGUE_CLOSURES: [{"question": "{Q-ID}", "answer": "{사용자 답변 요약}", "issue": "{한 줄}"}]
CONFIDENCE: HIGH | MEDIUM | LOW
```

### 출력 해석

- `MISSING_BRANCHES` 1개 이상 → Phase 0~2 질문 루프로 복귀하여 한 번에 하나씩 branch를 닫는다.
- `BAD_ORDER` 1개 이상 → 해당 downstream 결정이 upstream 답변과 충돌하지 않는지 사용자에게 한 번에 하나씩 재확인.
- `UNSUPPORTED_RECOMMENDATIONS` 1개 이상 → 권장 답안 근거를 코드/문서에서 보강하거나 사용자 승인 없이 반영된 내용을 제거.
- `OVER_QUESTIONING`은 blocker는 아니지만 skill 품질 결함으로 기록한다. 반복되면 `plan-issues` 자체 개선 후보.
- `UNDER_QUESTIONING` 1개 이상 → hard block. Phase 0~2로 복귀하여 누락된 Q-ID를 `open_questions`에 추가한다.
- `VAGUE_CLOSURES` 1개 이상 → hard block. 같은 Q-ID로 재질문하고 구체 답변을 받은 뒤 Phase 2.5를 다시 작성한다.

---

## 결과 집계 및 Block 게이트

4개 tier 결과를 단일 "검토 후보 리스트"로 통합하여 사용자에게 제시한다. 항목별로 (출처 tier, 영향 티켓 ID 또는 branch, 한 줄 설명) 표시.

T4의 `MISSING_BRANCHES`, `UNDER_QUESTIONING`, `VAGUE_CLOSURES`는 Soft Block이 아니라 hard block이다. 사용자에게 바로 기각 옵션을 주지 않고 Phase 0~2 질문 루프로 복귀한다. 각 항목은 stable Q-ID를 받아 `open_questions`에 들어간다.

### 제시 포맷

```markdown
## Phase 3.5 시뮬레이션 결과

총 {N}개 검토 후보 발견 ({T1=A건, T2=B건, T3=C건, T4=D건}, sub-agent 비용 ~${X}).

### T1: 모호함·silent assumption (티켓별)
- **T-1** AMBIGUITIES: {목록}
  - WHAT_I_WILL_BUILD가 본문에 없는 어휘 "{어휘}"를 사용 — silent assumption 후보
- **T-2** ...

### T2: DAG (Directed Acyclic Graph) 모순
- **T-3 → T-5**: T-5 본문이 "X 이벤트"를 가정하나 T-3은 "Y 이벤트"만 발행 (DAG_PARADOX)
- ...

### T3: Value Drift
- **SC-2**: T-4·T-7로 매핑되어 있으나 본문 acceptance scenario가 SC 검증 불가 (SUPERFICIAL_MAPPING)
- ...

### T4: Grill-me Interview Replay
- **domain model**: 구현 전 닫혀야 하는 branch가 스펙에 없음 (MISSING_BRANCH)
- **Q-3**: 권장 답안 근거가 코드/문서에 없음 (UNSUPPORTED_RECOMMENDATION)
- **rollout**: Mandatory Epic Grill Gate 없이 Phase 2.5 진입 (UNDER_QUESTIONING)
- **Q-error-1**: "일반적으로 처리" 답변을 재질문 없이 닫음 (VAGUE_CLOSURE)
- ...

### CONFIDENCE 분포
T1: HIGH=8, MEDIUM=2, LOW=0
T2: HIGH (전체)
T3: MEDIUM (SC-2 도달 가능성 불확실)
T4: HIGH (전체)
```

### Block AskUserQuestion (paranoid 강화)

charter §4-A에 따라 본 게이트는 plan 단계의 paranoid posture를 보호한다. 검토 후보 1개 이상이 발견되면 자동으로 사용자 질의한다 — 자기 판정으로 "전부 false positive"라 결론지어 우회하지 않는다.

먼저 hard block을 처리한다.

- T4 `MISSING_BRANCHES`, `UNDER_QUESTIONING`, `VAGUE_CLOSURES` 1개 이상 → Phase 0~2 질문 루프 복귀. 사용자에게는 "누락 질문 N개가 발견되어 이슈 생성 전 질문 루프로 돌아갑니다"라고 보고하고, 가장 upstream Q-ID 하나만 묻는다.
- hard block이 있으면 아래 soft block 선택지를 제시하지 않는다.

`AskUserQuestion`으로 일괄 의사결정 1회:

- **선별 수정 (default·권장)**: 선택한 항목만 Phase 2.5/3로 복귀하여 수정 → Phase 3.5 재실행. 선택은 사용자가 notes에 항목 ID 목록으로 입력.
- **전부 수용 → 복귀**: 발견된 모든 항목을 수정 대상으로 삼아 Phase 2.5/3 복귀.
- **전부 기각 → Phase 4**: false positive로 판단하여 무시하고 Phase 4 진입. **항목별 기각 사유 1줄 강제**(notes에 `T1#1: 사유`, `T2#1: 사유` 형식). 단일 사유 1줄로 전부 기각 금지 — 항목별 변별이 paranoid posture의 핵심.
- **재시뮬레이션**: 같은 입력으로 T1/T2/T3/T4 재실행 (LOW confidence 결과의 분산 확인).

Hard block이 없는 나머지 검토 후보는 false positive 비율 회피와 사용자 판단 우선을 근거로 soft block으로 처리한다. 단 charter §4-A의 paranoid posture를 보호하기 위해 (a) 자동 사용자 질의, (b) 항목별 기각 사유 강제, 두 장치를 적용한다. **Critical 1개 이상 시 "전부 기각" 선택은 강한 경고를 동반한다 (Soft Block).** 사용자 의지로 진행 가능하나 1줄 경고 노출.

### 복귀 정책

- T1 발견 → Phase 2.5 §4 (FR (Functional Requirement) 마커) 또는 §5-§8 (도메인 스펙) 갱신
- T2 발견 → Phase 3-1 (메타데이터) / Phase 3-3 (충돌 매트릭스) / Phase 3-4~3-6 (blockedBy) 갱신, Phase 3-8 draft 재생성
- T3 발견 → Phase 2.5 §10 (SC (Success Criteria)) 또는 Phase 3-6.5 (커버리지 매핑) 갱신, 자식 티켓 acceptance scenario 강화
- T4 발견 → Phase 0~2 질문 재개 또는 Phase 2.5 ledger/spec 반영. 한 번에 하나의 upstream branch만 다시 묻고, 권장 답안 근거를 코드·문서로 보강.

복귀 후 Phase 3.5 재실행 — false positive였던 항목은 같은 결과가 나와도 사용자 notes에 "기각" 기록된 ID는 자동 제외 (재제시 안 함).

---

## 비용 안전장치

| 조건 | 동작 |
|------|------|
| 자명 티켓 | T1/T2/T3/T4 전체 생략 |
| 단일 규모 (자명 아님) | T1 + T4, T2/T3 생략 |
| 그룹 규모 | T1 + T2 + T4, T3 생략 |
| 에픽 규모 | T1 + T2 + T3 + T4 |
| 티켓 ≥ 20개 | T1을 임의 선별 5개 + 크리티컬 패스 전체로 제한, 사용자에게 보고 |

비용 추정을 결과 보고 상단에 출력 (`sub-agent 비용 ~${X}`) — 사용자가 비용 인지하에 결정.

---

## 호출 절차 요약

1. 자명 조건 확인 → 충족 시 Phase 4로 직행.
2. 규모별 tier 선택 (위 안전장치 표).
3. 모든 sub-agent 호출을 단일 메시지에 묶어 병렬 발행.
4. 결과 집계 → 검토 후보 리스트 작성.
5. `AskUserQuestion`으로 Soft block 분기.
6. 복귀 또는 Phase 4 진입.
