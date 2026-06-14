---
description: 마일스톤/부모 이슈/이슈 묶음의 SDLC 전체를 무인 자동화하는 오케스트레이터. 의존 DAG (Directed Acyclic Graph) 웨이브 병렬로 각 이슈를 서브에이전트의 `/process-ticket --auto-merge`로 실행하고, 모든 머지 완료 후 마일스톤 의도 감사 + `/sync-docs`까지 수행한다.
argument-hint: "<milestone-name | #N | #101,#102,...>"
user-invocable: true
---

# Autopilot — 마일스톤 무인 자동화 오케스트레이터

> **궁극 목표**: 하나의 세션 내에서 **단일 부모 이슈 또는 단일 마일스톤의 end-to-end 구현을 성립시킨다.** 도중에 신규 후속 이슈이 쏟아져 나오더라도 **메인 세션이 sub-agent의 `spawned: ISSUE-NUMBER,...` 보고를 수신하는 즉시 background sub-agent로 spawn**하여 약속만 남기고 끝나는 것을 원천 차단한다 (`behavioral-guidelines.md` "후속 이슈 자동 실행 default = 즉시 분해" SSOT 정합). [Phase 3.5 회수 라운드](phases/phase-3_5-recovery.md)는 즉시 spawn이 누락된 ID만 흡수하는 **fallback fixed-point 게이트**로 동작한다. 모든 phase·결정·재시도는 이 목표에 종속된다.

본 스킬은 마일스톤 단위 업무 자동화 스킬이다. 한 번 호출하면 마일스톤이 끝날 때까지 사람이 개입하지 않는다 — **단, 기술적 모순(charter §4-A 의도 정렬, §4-B 질의 트리거)을 감지하면 즉시 stop & 사용자 질의**한다. 애매한 선호 판단만 자율 진행한다.

## 사용법

```
/autopilot 420                            # 부모 이슈 420의 모든 미완료 자식 이슈
/autopilot "마일스톤 이름"                # 해당 마일스톤 내 모든 미완료 이슈
/autopilot #101,#102,#103            # 지정 이슈 목록
```

### 인자 (필수)

대상 이슈 집합의 식별자. 자동 판별 (정규식 기반 — 모호하면 `사용자 질의`로 확인):
- `^#?\d+$` 형태 → **부모 이슈 ID**
- 쉼표(`,`) 포함 → **이슈 ID 목록**
- 그 외 → **마일스톤 이름**

## 본질

### 메인 세션 = 오케스트레이터, 이슈 SDLC = 서브에이전트

각 이슈의 분석·계획·구현·리뷰·CI 모니터링·코멘트 triage·머지는 서브에이전트(`/process-ticket --auto-merge`)가 수행한다. 메인 세션은 Phase 1-2(수집/DAG)·웨이브 결과 수집·Phase 4-6(감사/문서/리포트) 트리거만 담당한다.

서브에이전트 사용 이유:
1. **병렬성** — 같은 웨이브의 이슈를 동시 spawn하여 wall-clock 단축.
2. **메인 세션 컨텍스트 오염 회피** — 오케스트레이터가 N개 이슈의 SDLC 디테일을 누적 흡수하면 윈도우 폭발·지시 이탈·오동작이 발생한다. 서브에이전트는 격리된 컨텍스트에서 시작하여 결과 요약만 반환한다.

### 자율 진행 vs 사용자 질의

- **자율 진행** (사용자 질의 금지): 애매한 선호 판단(어느 옵션이 더 깔끔한가, 함수 시그니처 디테일, 변수명 등 — charter §4-B "자율 진행" 영역).
- **메인 블로커 fix 자율 진행**: CI red·hook 실패·import 깨짐 등은 무한 재시도로 근본 원인까지 추적 (charter §4-B "메인 블로커 회피 금지"). process-ticket Phase 6 LISTENING 루프가 담당.
- **gap 발견 → 자동 분해 default (자율 진행 영역, 질의 대상 아님)**: 실행 중 spec·code·harness·인접 도메인 gap을 인지하면 `behavioral-guidelines.md` "스펙 검증 / 후속 이슈"의 default(= 즉시 후속 이슈 분해 + 본 세션 백그라운드 spawn)를 그대로 적용한다. 이는 자율 진행 영역이며 사용자 질의 대상이 아니다 — gap 인지 자체가 default를 발동시킨다. `ask-delegate`를 "후속 이슈를 만들까요" / "분해해도 될까요" / "별도 PR로 빼도 될까요" 류 gap 회피 통로로 사용하는 것은 안티패턴이며, 메인의 ask-delegate 수신 처리(Phase 3 §3-3-quater)가 1차로 차단한다.
- **stop & 사용자 질의** (charter §4-A·§4-B 질의 트리거): 스펙↔코드 직접 충돌, 도메인 사전 미등록 신규 어휘, 이슈 분해 단위 재정의 필요(분해 자체에 대한 비즈니스 의도 공백 — "분해할지 말지"가 아니라 "어떤 단위로 분해할지"), 정책·규칙 위반 가능성, 외부 시스템 destructive mutation. **기술적 모순을 무인 자동화 명목으로 녹여 기술 부채로 만들지 않는다.** 동시에 위 트리거에 해당하지 않는 gap을 "사용자 결정 필요" 라벨로 끌어올려 자동 분해 default를 약화시키지도 않는다 — 트리거 경계는 양방향 보존된다.

### 머지 정책

- `gh pr merge --auto`, `--admin` flag는 어떤 경우에도 사용하지 않는다.
- 머지는 process-ticket Phase 6의 monitor → triage → monitor 루프로 PR이 **CLEAN 상태(CI green + 모든 코멘트 처리 완료 + reviewDecision=APPROVED)** 에 도달한 직후, agent가 `gh pr merge --squash --delete-branch`를 직접 호출하여 수행한다 (`--auto-merge` 플래그 동작).
- claude bot 리뷰 자동승인 환경을 활용하여 외부 코멘트(대부분 bot)를 triage 루프 안에서 흡수한다. 사람 리뷰어 코멘트가 들어오면 triage가 수용/반박을 판정하고, 반박 케이스에서 사람 응답을 기다려야 하면 해당 PR은 awaiting-review로 두고 후속 웨이브 중 그 가지에 의존하는 노드만 차단(독립 가지는 계속 진행).

### 사용자 질의 단일 채널

sub-agent의 질의(charter §4-A 트리거·plan 승인·review escalation·머지 승인)는 모두 SendMessage `ask-delegate`로 메인(team-lead)에 위임된다 (`/process-ticket` SKILL.md "사용자 질의 위임" 정합). 메인이 user-facing 단일 채널을 보유 — sub-agent 직접 `사용자 질의`를 호출 0건. 메인은 `ask-delegate` 수신 시 self_check 결과에 따라 즉시 채택 또는 `사용자 질의`를 호출을 분기한다 (Phase 3 §3-3-quater SSOT).

### 후속 이슈 GitHub 메타데이터 계약

gap 후속 이슈은 **현재 autopilot 실행의 같은 작업 묶음**이다 — `spawned: ISSUE-NUMBER,...` 보고는 ID만으로 불충분하며, 메인은 spawn 전에 `team`·`project`·`projectMilestone`·`assignee`·라벨 최소 집합(원본의 비용/계층/작업 성격 3종 — 미존재 라벨명 신규 생성 금지)을 재조회·보정·재검증한다. 기대값(source 이슈 snapshot 1차, `autopilot_metadata_context` fallback)·보정·검증·보류 절차는 `phases/phase-3-wave-loop.md` §3-3-quinque "후속 이슈 즉시 spawn" SSOT. sub-agent는 검증까지 끝난 ID만 `spawned`·`gaps_dispatched`에 보고한다 — 미검증 ID 보고·보정 실패의 `notes:` 은닉은 gap-defer와 동일한 실패.

---

## 진행률 정형 (사용자 알림 prefix)

메인이 사용자에게 출력하는 **모든** `[autopilot] ...` 1줄 알림(wave/후속/stuck/fallback/메타 fix 알림, sub-agent ping 표시 포함)에 다음 prefix를 부착한다. **예외 3종 (부착 금지)**: Phase 6 §6-1 최종 리포트(자체 형식) / 사용자 질의 본문(`사용자 질의`·`ask-delegate` 처리 보고 — 시각적 잡음) / abort·exit 메시지(charter §4-A stop 보고).

```
[autopilot {N}/{M} ({P}%) ETA {Xh Ym}] <메시지 본문>
```

- **`N`** — `wave_results` terminal status(`merged`/`awaiting-review`/`failed`/`skipped`) 누적 이슈 수.
- **`M`** — Phase 1 §5 확정 `total_issue_count`. **M 갱신 (본 정의가 단일 기술 지점)**: Phase 3.5 재귀 진입 직전 `total_issue_count += len(누락 spawn 집합)` — 진행률 일시 후퇴는 "총 작업량 증가"를 알리는 올바른 신호, 자의적 가중치 금지 (`behavioral-guidelines.md` "자의적 임계값 금지" 정합).
- **`P`** — `round(N * 100 / M, 1)`. `M == 0`이면 `100.0` (정상 빈 결과 종료).
- **`ETA`** — `N == 0` → `--h --m` (측정 불가) / `N == M` → `0h 0m` / 그 외 → `(now − start_ts) × (M − N) / N`을 시·분으로 표기.
- **`start_ts`** — Phase 1 §5 보고 직후 1회만 기록. Phase 3.5 재귀 라운드에서도 동일 값 유지 (가장 바깥 진입부터의 누적).

**출력 직전 자가검사 (의무, 외부 게이트)**: `start_ts`·`M`이 실행 상태 사전에 존재하고 `N`·ETA를 위 정의대로 산출했는가 — 하나라도 No면 본 turn의 prefix 출력 자체가 정형 위반, 누락 필드 보고 + 상태 사전 보강 후 재계산한다. **`N > 0`인 turn에서 `ETA --h --m` placeholder 출력 = 위반** — self-confirmation bias로 placeholder가 통과하지 않도록 하는 행동 테스트 게이트.

---

## Phase 개요

각 Phase 진입 시 해당 파일을 Read로 로드하여 단계별 절차를 적용한다.

| Phase | 책무 | 상세 |
|-------|------|------|
| **Phase 1** | 대상 이슈 수집 (dual-path 수렴 게이트) — 마일스톤 ID 해석 / project 페이지네이션 / 부모 epic 추출 + parentId 트래버스 / 수렴 실패 시 §3.6-2 자동 fix 이슈 | `phases/phase-1-collection.md` |
| **Phase 2** | DAG 구성 & 웨이브 계산 — 부모 epic 의존 재작성 + 위상정렬 | `phases/phase-2-dag.md` |
| **Phase 3** | 웨이브 실행 루프 — 병렬 진입 / 반환 대기 / stuck 능동 감지 / 실패 전파 / fallback | `phases/phase-3-wave-loop.md` (+ 조건부 Read: PR 머지 이벤트 시 `phases/ledger-bot-violations.md`, 신규 이슈 생성·편입 시 `phases/new-ticket-intake.md`) |
| **Phase 3.5** | 후속 이슈 회수 라운드 (fixed-point) | `phases/phase-3_5-recovery.md` |
| **Phase 3.6** | 자기 운영 결함 자동 감지·이슈화 (메타-자동화) | `phases/phase-3_6-meta-detection.md` |
| **Phase 4** | 마일스톤 의도 감사 (서브에이전트 위임) | `phases/phase-4-intent-audit.md` |
| **Phase 5** | 문서 동기화 (`/sync-docs` 서브에이전트 위임) | `phases/phase-5-sync-docs.md` |
| **Phase 6** | 최종 리포트 — 부모 epic 자동 Done / 잔존 워크트리 sweep / 리포트 출력 | `phases/phase-6-final-report.md` |

---

## 규칙

본문·phase 파일이 보유한 규칙은 재기술하지 않는다 — 아래는 본 섹션이 단독 보유하는 항목만.

- **서브에이전트 `model` 티어링**: §3-2 wave spawn은 미지정(전 Phase 혼재 — process-ticket 내부 티어링 위임) / §3-3-bis 상태 흡수형 resume(모순 A·C·E, terminal-return 회수)은 `model: sonnet` 명시 / 모순 B(conflict resolution) resume은 미지정.
- 모든 서브에이전트 반환은 **구조화된 단일 메시지로 압축** — 진행 과정·디버깅 로그·중간 추론 반환 금지 (정형·줄 상한은 각 phase 파일이 정의).
- 각 Phase 전환 시 사용자에게 현재 단계를 간결하게 알린다.
- **autopilot 메인 세션은 PR 상태 직접 polling 금지** (`gh pr view ... mergeStateStatus` Bash `until`-loop 등) — monitor/merge는 서브에이전트(`/process-ticket --auto-merge`) 책임. 예외는 Phase 3.6 메타-감지 한정 (`phases/phase-3_6-meta-detection.md` §3.6-3 SSOT). monitor 도달 전 조기 종료·monitor 내 stuck 미반환은 Bash polling 떠맡기가 아니라 **resume 서브에이전트 spawn**(§3-6 fallback / §3-3-bis 능동 감지 — 워크트리 state 단발 query는 polling 금지 범위 외)으로 회수한다.
- **GitHub MCP tool prefix는 `GitHub connector/gh *`** — 구식 prefix 사용 금지.
- **sub-agent `skill-unavailable` 보고 수신 시** §3-6 fallback과 동등 escalation — charter §4-A 트리거(기술적 모순)로 사용자 질의로 이어진다.
