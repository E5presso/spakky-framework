# 행동 원칙

## 1. Think Before Coding

- 불확실하면 가정하지 말고 묻는다.
- 해석이 여러 개면 전부 제시한다. 조용히 하나만 골라 진행하지 않는다.
- 더 간단한 방법이 있으면 먼저 말한다.

## 2. Simplicity First

- 요청 범위 밖 기능·유연성·설정 가능성을 추가하지 않는다.
- 단일 사용 코드에 추상화 / 헬퍼 함수 추출 금지. 2곳에서 반복되는 짧은 로직도 인라인이 낫다. 2개 이상 모듈이 공유하면 모듈 수준 허용.
- **자명한 단일 사용 변수는 인라인.** 바로 다음 줄에서만 쓰이고 오른쪽 식이 자명하면 변수 선언 금지. 이름이 의미 전달에 기여할 때만 유지.
- **pass-through `__init__` 금지.** `super().__init__(*args, **kwargs)`만 호출하는 생성자 작성 안 함.
- **defensive `None` 허용 금지.** 도메인이 `None`을 보장하지 않으면 `Optional` 선언 안 함.
- **필요 없는 wrapper / resolve 레이어 제거.**
- **헬퍼·Repository·Service·도메인 함수 1회 호출만 위임하는 pass-through UseCase·Service·Adapter 금지** — Inbound boundary 가 아닌 위치(UseCase ↔ UseCase 위임, agent code 의 도구 catalog 외부 wrapping)에 한해 적용. Inbound Adapter (`adapters/apis/`·`adapters/messaging/`) 가 호출하는 UseCase 와 `@class_tool_metadata`/`@method_tool_metadata` tool surface 는 wrapping 동기가 명확한 boundary 계약 정의이므로 면제 (memory `feedback-no-helper-wrapper-usecase` SSOT, `domain/usecases/` 는 USECASE-PASS-001 정적 게이트로 차단).
- **Imperative 루프는 comprehension 또는 named phase로 분해.** `done` 플래그·중첩 `break`·상태 변수 루프는 가독성 해침.
- **깊은 분기는 early return으로 평탄화.** 정상 흐름을 중첩 `else` 밑에 두지 않음.
- **커스텀 sort 구현 금지.** `sorted(key=..., reverse=...)`로 풀릴 문제에 비교 함수 작성 안 함.
- **소유권이 명확한 함수는 클래스에 귀속.** 특정 클래스에서만 호출되는 private 함수는 `@staticmethod`로.
- **50줄 이상 orchestrator는 named phase로 분해하거나, 각 구간에 `# Phase N:` 주석.** "주석 금지" 원칙의 예외.
- 200줄을 50줄로 줄일 수 있으면 다시 쓴다.
- **성능 + 가독성 동시 보전** (charter §2 차원 #5). 가독성 우선 작성이 default. 단 다음 명백 안티패턴은 가독성 핑계로 둘 수 없다 — 작성 시점에 회피한다:
  - 루프 안의 N+1 DB·외부 API 호출 (배치·prefetch로 평탄화)
  - O(N²) 명백 패턴 (정렬/set·dict 인덱싱으로 O(N log N)·O(N))
  - 반복적 직렬화/역직렬화 (1회 직렬화 후 캐시)
  - 동일 객체 재계산 (간단한 메모이제이션·지역 변수 캐시)
  - 메모리 적재가 명백히 큰 데이터(10만 건+)를 streaming 없이 list로 적재
  미시 최적화(루프 풀기·내장 함수 substitution 등)는 hot path 식별 후에만. 그 외는 가독성 우선.

## 3. Surgical Changes (컨텍스트 윈도우 관리)

한 에이전트 루프는 단일 변경 범위에 집중한다 — 컨텍스트 오염·지시 이탈·롤백 비용 방지가 목적이며, 작업 미루기의 근거가 아니다. 추가 작업이 발견되면 다음 세션이 아니라 같은 세션의 새 서브에이전트 루프로 분기한다.

- **PR close 금지.** CI 재트리거를 위해 close/reopen 하지 않는다. CI 실패 시 원인 조사 후 재push.
- **force-push 기본 금지, rebase push 예외.** PR 을 닫거나 새 PR 로 갈아타기 위해 force-push 를 쓰지 않는다. 단, 이미 열린 PR 브랜치를 `origin/develop` 위로 rebase 한 결과를 같은 원격 브랜치에 반영하는 경우에 한해 `git push --force-with-lease` 를 허용한다. 이 예외는 rebase push 전용이며 CI 재트리거·빈 커밋 대체·히스토리 정리 목적에는 사용하지 않는다.
- **pre-commit 테스트 우회 금지.** `PRECOMMIT_SKIP_TESTS=1`·`--no-verify` 등 훅을 우회하여 커밋/푸시하지 않는다. 테스트/훅 실패는 근본 원인 수정으로 해결하고, 인프라 미기동 등으로 일시 차단되면 사용자에게 보고 후 판단을 받는다.
- **import와 사용 코드를 한 번에 추가.** import만 먼저 넣으면 ruff가 즉시 제거하여 루프 발생.
- **"이왕 하는 김에" 금지.** 버그 수정에 리팩터링 끼우지 않음. 별도 커밋/PR로 분리.
- **변경된 모든 라인이 사용자 요청에 직접 연결되는가?** 연결 안 되면 되돌린다. 인접 코드/주석/포매팅 "개선" 금지.
- **기존 기술 교체/제거 전 사용자 확인.** "X를 활용해줘"는 "Y를 제거해줘"가 아님.
- **장애물은 우회 말고 근본 원인 추적.** 안 되면 사용자에게 보고.
- **`git push` 후 remote 반영을 반드시 검증.** push 명령 한 번의 "ok/exit 0"만으로 반영되었다고 판단하지 않는다. 매 push 직후 `git rev-parse HEAD` 와 `git rev-parse @{u}` (또는 `git log origin/<branch> -1`) 를 비교하여 local HEAD가 remote에 실제로 도달했는지 확인한다. 불일치 시 `git push origin <branch>` 로 명시적 재시도. 사용자가 "PR에 파일이 안 보인다"라고 지적하기 전에 detect해야 한다.
- **push 출력을 `tail -N` 등으로 자르지 않는다.** git이 upstream 미설정·non-fast-forward·reject 등 중요한 경고를 전체 stderr 중간에 뱉을 수 있으므로 full 출력을 읽는다.
- **스코프 확장은 같은 세션의 새 서브에이전트 루프로 분기.** 후속 이슈를 만들고 `Agent` tool로 즉시 시작한다. 다음 세션 위임 금지 — 분할은 동시 실행으로 처리량을 늘리는 도구이지 작업 종료 사유가 아니다.
- **CI fail default 진단 = 코드/테스트 결함.** PR (Pull Request) CI (Continuous Integration) 실패를 환경 측 결함("인프라 차단"·"runner loss"·"job 설정 오류" 류)으로 분류하려면 다음 명시 시그널 1개+ 인용 필수: 1) GitHub Actions workflow syntax/parse error 로그, 2) CI runner disconnect/executor unavailable, 3) Docker 미기동·외부 dependency 미주입 명시 로그, 4) Branch protection rule 위반, 5) CI provider 자체 outage/status page. GitHub Actions 로그 본문 인용(`gh run view --log` 또는 GitHub connector 로그 조회)이 환경 차단 분류의 선행 조건 — 로그 조회 생략/실패/미인용 상태의 인프라 추정은 동일 회피 경로이며, 인증 부재는 사용자에게 재인증을 요청한 뒤 재시도. 본 PR이 회귀 가능성 종류(미들웨어 추가·global dependency·공유 fixture·전역 라우팅 변경)일수록 "코드 회귀" default 정당화 강도 상향 — plan 시점에 자체 메모.

## 4. Goal-Driven Execution

- 작업 전 성공 기준을 정의하고 검증될 때까지 반복한다. `[단계] → 검증: [체크]` 형태.
- "버그 수정" → "재현 테스트 작성 후 통과".
- "리팩터링" → "전후 테스트 통과 확인".

## 사용자 질문 방식

- **사용자 질의는 구조화된 선택지 우선**. 가능한 경우 유력 옵션에 `(권장)`을 붙이고, 선택지로 표현되지 않는 맥락만 자유 입력으로 묻는다.
- **질문 호출 전 출력창에 4요소 배경 의무** (비개발자도 판단 가능한 수준): 1) 현재 상황 2) 결정이 필요한 이유 3) 각 선택지의 결과 4) 권장안의 근거(출처 1줄 인용). 검증 자문: "도메인 모르는 동료가 이 출력만 보고 5초 안에 고를 수 있는가?" No면 다시 쓴다.
- **언어 규칙**: 기술 약어·아키텍처 명사는 괄호 풀이 병기(예: "Port(외부 시스템과 도메인을 잇는 입출력 계약)"). 도메인 사전의 한국어 표현 우선. `label`은 결과물 어휘, `description`은 즉각적 결과 1줄 — 약어·코드 식별자만으로 라벨 구성 금지. `(권장)` 옵션 `description`에는 결과 1줄 + 근거 1줄(출처 인용).
- **자가검사 의무 출력 (사용자 질의 직전)** — 미출력 질의는 자가검사 미실시로 간주, 자기 점검 후 재진입:
  ```
  자가검사:
  (a) 본문/사전/하네스에서 도출 가능? <Yes/No — 1줄 근거 (출처 인용)>
  (b) 권장안이 다른 옵션 대비 명백히 우월? <Yes/No — 1줄 근거>
  (c) 1~2줄로 채택 근거 설명 가능? <Yes/No>
  ```
  - 셋 다 Yes → **질의하지 않고** 권장안 즉시 실행 + 1~2줄 근거 보고 (사용자는 회신으로 되돌릴 수 있다). 하나라도 No → 그 No 항목을 본문에서 인용하며 질의.
  - **예외 (반드시 묻기, 자가검사 출력도 의무)**: 되돌리기 어려운 작업(PR 병합·브랜치 삭제·외부 메시지 발송·destructive action), 사용자 요청 범위 확장 가능성.
  - **분류 라벨("정책 결정"·"운영 결정" 등)은 자동 질의 트리거가 아니다** — (a)에서 SSOT를 실제 grep·read한 결과만 트리거 자격. confidence가 의심스러우면 묻는다.

## 네이밍

- **신규 심볼 도입 전 의도를 사용자에게 설명하고 합의.** 기존 패턴 답습도 "논의 없는 결정"으로 간주.
- **통상 개발 용어 무단 채택 금지**: `payload`, `schema`, `edge`, `match`, `link`, `pair`, `sample`, `inference`, `overrides`, `member`, `Converter` 등을 설명 없이 도입 금지.
- **프로젝트 문서 미등록 용어는 코드에 넣기 전 등록 위치를 합의**한다. 도메인 용어는 `AGENTS.md`, `ARCHITECTURE.md`, 패키지 README, 관련 ADR 중 실제 코드와 일치하는 문서를 우선한다.
- **팀 확정 용어는 대체어로 바꾸지 않는다.** 변경이 필요하면 사전 갱신부터.
- **축약어는 문서/파일 내 최초 1회 풀이 병기.** 형식: `축약어 (풀어 쓴 용어)` — 예: `FP (False Positive)`, `VO (Value Object)`. 동일 파일 내 반복은 축약어만 사용 가능. 도메인 사전 등재 여부와 무관하게 적용 — 외부 독자가 의미를 추적할 수 있어야 한다.

근거 예시: "`member`라는 용어를 쓰셨는데 이 도메인은 이미 `Entry`로 합의되어 있습니다."

## 스펙 검증 / 후속 이슈

- **스펙 오류 감지 시 작업 도중이라도 보고.** 외부 스펙(GitHub, API spec, 데이터 모델)이 현재 코드/도메인과 어긋나면 조용히 따라가지 않는다.
- **gap 인지 = 같은 세션 내 후속 이슈 생성 + spawn (즉시 분해 의무).** spec gap·code gap·harness gap·인접 도메인 어긋남 전 카테고리 동일 적용. 기록만 남기는 모든 형태(PR 본문·`notes:`·코멘트·질의 카드·"backlog"·"별도 후속"·"보고만" 류 어법)는 미루기로 간주하여 차단 — 외부 게이트는 charter §5 게이트 4 (gap-defer 차단) SSOT.
- **분해 여부는 사용자 결정 항목이 아니다.** "후속 이슈를 만들까요" 류 질의는 default(=즉시 분해) 재확인 회피 행동. default를 약화시키려면 charter §4-A 질의 트리거(스펙↔코드 직접 충돌·미등록 어휘 도입·분해 단위 재정의의 비즈니스 의도 공백·destructive 승인) 중 하나가 동반되어야 한다.
- **실행 경로**: `/plan-issues`로 이슈 생성 → 본 세션 백그라운드 서브에이전트로 `/process-ticket {신규-ISSUE-NUMBER}` 즉시 실행. 현재 작업 범위에 끼워넣지 않고(=Surgical) 다음 세션으로 미루지도 않는다(=능동 실행). 즉시 분해가 무의미한 경우(동일 파일 머지 충돌 예상)에만 `/schedule` durable remote routine 허용 — **휘발성 스케줄러(`CronCreate` session-only·`ScheduleWakeup`·로컬 cron·sleep 루프) 절대 금지** (세션 종료 시 약속 유기). 상세는 `/triage-comments` SKILL.md "후속 이슈 생성".
- **GitHub 메타데이터 상속 필수**: 후속 이슈는 원본 이슈의 milestone·assignee·labels·project 연결(사용 중인 경우)을 상속한다. 원본이 비면 Phase 1 anchor + 동일 마일스톤 기존 이슈의 라벨 집합 사용. 생성 직후 `gh issue view` 또는 GitHub connector로 재조회하여 검증 — 누락 채 번호만 보고는 "이슈만 만들고 끝"과 동일한 실패.
- **의존 관계 필수 설정**: 현재 이슈 자동 blocker 금지(파일럿/형제 가능성) / 단, 현재 PR 산출물에 직접 의존하면 현재 이슈를 선행으로 표기 / 진짜 blocker = 공유 인프라(Port·매퍼·공용 API·선행 패턴) 정의 이슈 — 동일 마일스톤에서 탐색(`gh issue list` 또는 GitHub connector + milestone 필터) / 공유 인프라 없으면 blocker 없음도 유효(임의 이슈 금지) / 생성 직후 이슈 본문·sub-issue·project dependency 등 repo가 쓰는 실제 표기 경로를 확인한다.
- 자주 놓치는 축: aggregate 경계, 동기 vs 비동기 경계, 인프로세스 vs 외부 이벤트 경계, 동시성·트랜잭션 범위.
- **스펙 문서 필드가 도메인 모델에 1:1 매핑되지 않는다.** 파생 데이터(자동 계산·캐시·인덱스)는 도메인이 아닌 적절한 인프라/어댑터 모델에 둔다.

## 정보 우선순위

외부 스펙(GitHub Issue 등)과 하네스·코드베이스가 충돌하면 **하네스·코드베이스 우선**. 판단이 어려우면 사용자에게 확인.

하네스 작성 / 수정 규칙은 `harness-writing.md` 참조.
