# 문서 포맷 가이드 & 문서별 작성 규칙

Writer가 작성하는 모든 문서는 아래 포맷 규칙을 따른다. Verifier도 포맷 위반을 지적한다.

## 문서 포맷 가이드

### 구조

- **문서 상단에 1~2문장 요약** (`>` blockquote).
- **목차는 작성하지 않는다** — 렌더러가 자동 생성.
- **섹션은 `##`부터 시작** — `#`은 문서 제목에만.
- 패키지 README, ARCHITECTURE.md 등 기존 파일에는 frontmatter를 강제하지 않는다 (각 파일의 기존 컨벤션을 따른다). ADR은 `docs/adr/` 자체 frontmatter 규칙을 따른다.

### 다이어그램 (필수: Mermaid)

- **모든 시각화는 Mermaid로 작성한다. 예외 없음.**
- ASCII art, 텍스트 박스 다이어그램, 유니코드 선 그림은 **절대 금지**.
- Verifier는 Mermaid가 아닌 시각화를 발견하면 **Critical**로 지적한다.
- 용도별 Mermaid 타입:

| 용도 | Mermaid 타입 |
|------|-------------|
| 의존 관계, 데이터 흐름 | `flowchart` (또는 `graph TD`) |
| 요청/응답 흐름, 시퀀스 | `sequenceDiagram` |
| 클래스 구조, Aggregate·Port 관계 | `classDiagram` |
| 상태 전이, Saga 단계 | `stateDiagram-v2` |
| 타임라인, 마일스톤 | `timeline` |

- 노드 라벨은 한국어 가능하되, 코드 식별자(클래스명, 모듈명, 패키지명)는 영문 그대로.
- 추가 가이드라인은 `.claude/rules/mermaid.md` 참조 (중첩 서브그래프, 인라인 엣지, 노드 색상).

### 테이블

- 열이 4개 이하면 Markdown 테이블. 5개 이상이면 테이블을 분리하거나 축약.
- 셀 내 긴 텍스트는 핵심만 남기고 줄인다.

### 코드 참조

- 인라인 코드: `` `ClassName` ``, `` `method_name()` ``, `` `@Configuration` ``
- 코드 블록은 언어 태그 필수: ````python`, ````yaml`, ````toml` 등.
- **실제 코드를 그대로 복사하지 않는다** — 시그니처와 패턴만 보여준다.

### 서술 스타일

- 코드를 나열하지 말고 **소화하여 서술**한다. "X 클래스가 있다, Y 클래스가 있다" 대신 "X가 Y를 통해 Z를 수행하며, 이 과정에서 W 패턴을 따른다."
- 코딩 에이전트가 읽고 바로 따라할 수 있는 **규범적(prescriptive) 톤**으로 작성한다.

### 용어

- 도메인 용어는 `CLAUDE.md` "프로젝트 특수 컨벤션" 섹션과 `ARCHITECTURE.md`의 도메인 어휘를 따른다.
- 영문 기술 용어는 번역하지 않는다 (Aggregate, Port, UseCase, Aspect, Plugin, Repository 등).
- 축약어는 등장 시 풀이 병기 (`behavioral-guidelines.md` "네이밍" 참조).

---

## 문서별 작성 규칙

Writer 프롬프트에 대상 문서에 해당하는 규칙을 포함한다.

### ARCHITECTURE.md

> "새 코드를 어디에 어떻게 놓지?"

**소스**: `core/*/src/`, `plugins/*/src/` 전체 구조 + 패키지 간 import 관계 + `pyproject.toml` 의존성 선언

모노레포의 레이어 구조, 패키지별 책임, 의존 방향, 파일 배치 패턴을 종합 서술한다. 단순 디렉토리 트리가 아니라 "이런 종류의 코드는 이 패키지/레이어에 이런 패턴으로 놓는다"는 규범을 제시한다.

포함 내용:
1. 패키지별 역할과 책임 (core: spakky / spakky-domain / spakky-data / spakky-event / spakky-task / spakky-tracing / spakky-outbox / spakky-saga, plugins: 각 통합 어댑터)
2. core ↔ plugins, plugin ↔ plugin 의존 방향 — Mermaid `flowchart` 또는 `graph TD`로 시각화 (단방향 보장)
3. 각 패키지 내 레이어 배치 패턴 (예: "UseCase는 `domain/usecases/`, Aspect는 `aop/`, Port는 `ports/` 아래에 둔다")
4. 금지 패턴 (도메인 → 인프라 import 금지, plugin → 다른 plugin 직접 import 금지, 역방향 의존 금지)
5. 신규 기능 추가 시 "어디에 무엇을 만들어야 하는가" 가이드 (신규 패키지 추가 기준 포함)

### docs/adr/ — Architecture Decision Records

> "이 설계 결정의 배경과 근거는?"

**소스**: 기존 `docs/adr/*.md` + 코드에서 확인 가능한 결정 이력

ADR은 `docs/adr/` 디렉토리에 개별 파일로 관리한다.

파일명 규칙: `NNNN-<slug>.md` (예: `0001-hexagonal-architecture.md`).

각 ADR의 구조:
```markdown
---
title: "ADR-NNNN: 결정 제목"
date: 'YYYY-MM-DD'
status: accepted | superseded | deprecated
superseded_by: NNNN (해당 시)
---

# ADR-NNNN: 결정 제목

## 맥락
(결정이 필요했던 상황)

## 결정
(선택한 방향과 이유)

## 대안
(검토했지만 선택하지 않은 옵션과 탈락 이유)

## 결과
(이 결정으로 인한 영향 — 코드에서 확인 가능한 것)
```

Verifier의 ADR 검증:
- `status: accepted`인 ADR의 결정이 현재 코드에 실제로 반영되어 있는지 확인.
- 코드와 불일치하면 Warning ("ADR-0003의 결정이 코드에서 뒤집어져 있음").
- `status: deprecated`인 ADR이 코드에 여전히 반영되어 있으면 Warning.
- `docs/adr/README.md`의 인덱스가 실제 파일 목록·status와 일치하는지 확인.

### 도메인 모델 (Aggregate / Entity / ValueObject / Event)

> "도메인 개념 간 관계와 제약은?"

**소스**: `core/spakky-domain/src/`, 각 플러그인의 도메인 레이어

> 본 프로젝트에는 별도의 `domain-model.md`가 없다. 도메인 모델 서술은 `ARCHITECTURE.md`의 "도메인 빌딩 블록" 섹션 또는 `core/spakky-domain/README.md`에 둔다. 신규 도메인 개념이 이 두 곳에서 모두 누락되어 있으면 Writer가 적절한 위치에 섹션을 추가한다.

Aggregate 간 관계, 불변식(invariant), 비즈니스 규칙을 하나의 서사로 종합한다. 클래스를 나열하지 말고, 도메인이 어떻게 작동하는지를 설명한다.

포함 내용:
1. 도메인 빌딩 블록 전체 구조 — Mermaid `classDiagram`으로 Entity / AggregateRoot / ValueObject / Event 관계 시각화
2. 각 AggregateRoot의 책임과 불변식
3. ValueObject·Enum의 역할
4. Port 인터페이스가 도메인에서 어떤 계약을 표현하는지
5. AggregateRoot 간 참조 규칙 (ID 간접 참조, Event 발행 경유 등)

### Port / UseCase 카탈로그

> "어떤 입출력 계약과 시나리오가 정의되어 있는가?"

**소스**: 각 패키지 `ports/`, `domain/usecases/` 또는 동등 위치

Port와 UseCase를 개별 나열하지 말고, **카테고리별 패턴**으로 서술한다. 새 Port·UseCase를 추가할 때 기존과 일관되게 설계할 수 있는 규범을 제시한다.

포함 내용:
1. Port 분류 (입력 Port = Driving / 출력 Port = Driven, 또는 Repository / Publisher / Consumer / Gateway 등)
2. UseCase 명명 패턴 (Command / Query 구분, `IAsync*UseCase` vs 동기 `*UseCase`)
3. Port 시그니처 작성 규약 (Awaitable 반환, 예외 계약, Optional 의미)
4. 현재 Port·UseCase 요약 테이블 (위치, 책임 — 1줄씩, 5개 이상이면 카테고리별 분리)
5. 패키지별 README에 둘지, ARCHITECTURE.md에 둘지의 배치 기준

### Plugin 카탈로그 (`plugins/*/README.md`)

> "이 플러그인은 어떤 통합을 제공하는가?"

**소스**: `plugins/<name>/src/`, `plugins/<name>/pyproject.toml`, `entry-points`

각 플러그인 README는 다음 구조를 따른다:

1. 1줄 요약 (어떤 외부 시스템·프레임워크를 통합하는가)
2. 제공하는 컴포넌트 (어댑터, Aspect, Configuration, Controller 등) — Mermaid `classDiagram` 또는 표
3. 의존 core 패키지 목록과 사용 패턴
4. 다른 플러그인에 의존하는지 여부 (원칙적으로 금지, 예외 시 사유 명시)
5. 사용 예 (DI 등록, 설정값) — 시그니처 패턴만, 풀 코드 복사 금지
6. 환경변수·설정 키 매핑 (있는 경우)

### AOP Aspect 카탈로그

> "어떤 횡단 관심사가 Aspect로 모듈화되어 있는가?"

**소스**: `core/*/src/**/aop/`, `plugins/*/src/**/aop/`, `@Aspect`/`@AsyncAspect` 데코레이터 사용처

포함 내용:
1. 정의된 Aspect 목록 (위치, 동기/비동기 쌍 여부)
2. 각 Aspect의 pointcut 정의 패턴
3. Aspect 작성 시 `.claude/rules/aspect.md` 규약 요약 (동기/비동기 쌍 의무, pointcut 표현)
4. Aspect 우선순위·순서 결정 규칙 (있는 경우)

### conventions / `CONTRIBUTING.md`

> "기존 코드와 같은 스타일로 쓰려면?"

**소스**: `core/*/src/`, `plugins/*/src/` 전체에서 실제 패턴 추출 + `.claude/rules/python-code.md`, `.claude/rules/test-writing.md`

코드에서 실제로 사용되는 패턴을 관찰하여 규범으로 정리한다. 문서화된 규칙이 아니라 코드에 실재하는 패턴이 기준이다.

포함 내용:
1. 네이밍 패턴 (클래스, 함수, 변수, 모듈, 패키지)
2. 타이핑 패턴 (PEP 695 generic, `X | None`, `@override`, `typing.Self` 등 실제 사용례)
3. 에러 처리 패턴 (`SpakkyException` 또는 도메인 에러 상속 구조, `ErrorCode` 사용법, `assert` 금지·빌트인 raise 금지)
4. 테스트 패턴 (함수 기반, fixture, 단위/통합 구분, `class TestXxx` 금지)
5. import 패턴 (절대 import, 패키지 간 import 규칙, plugin → plugin 금지)

### 도메인 사전 / 프로젝트 특수 컨벤션 (`CLAUDE.md`)

> "이 용어의 정확한 의미와 네이밍은?"

**소스**: `CLAUDE.md` "프로젝트 특수 컨벤션" + `ARCHITECTURE.md` 도메인 어휘 + 코드 대비 검증

> 본 프로젝트에는 독립된 `domain-dictionary.md`가 없다. 도메인 용어 정의는 `CLAUDE.md`의 "프로젝트 특수 컨벤션" 섹션과 `ARCHITECTURE.md`에 분산되어 있다. 신규 용어 등록은 `behavioral-guidelines.md` "네이밍" 절차(사용자 합의 후 사전 등록)를 따른다.

포함 내용:
1. 도메인·아키텍처 용어 정의 (코드에서 실제 사용되는 식별자와 매핑)
2. 용어 간 관계 (상위/하위, 동의어, 혼동 주의)
3. 네이밍 규칙 (코드에서 이 용어를 변수명/클래스명으로 쓸 때의 패턴)
4. **코드에 없는 용어는 제거한다** — 계획 단계에서만 존재했던 용어는 사전에 남기지 않는다.

### API surface (`plugins/spakky-fastapi`, `plugins/spakky-typer`, `plugins/spakky-grpc` 등)

> "새 API/엔드포인트를 기존과 일관되게 설계하려면?"

**소스**: 각 컨트롤러 플러그인의 사용처 패턴, `@RestController` / Typer command / gRPC servicer 정의

개별 엔드포인트를 나열하지 말고, API 설계 철학과 패턴을 서술한다.

포함 내용:
1. 컨트롤러 구성 패턴 (prefix, 태그, 버저닝, command 그룹)
2. 요청/응답 스키마 설계 패턴 (Pydantic BaseModel 구조, DTO 매퍼, 네이밍)
3. 에러 응답 패턴 (상태 코드 사용 규칙, 에러 본문 구조, 도메인 에러 ↔ HTTP/gRPC status 매핑)
4. 인증/인가 패턴 (`spakky-security` 통합, 있는 경우)
5. 현재 엔드포인트·command·서비스 요약 테이블 (경로/이름, 메서드, 용도 — 1줄씩)

### tech-decisions / 의존성 정책

> "왜 이 기술을 쓰고, 어떻게 활용하지?"

**소스**: 루트 `pyproject.toml` + 각 패키지 `pyproject.toml` + 코드 내 실제 사용 패턴

기술 선택의 이유와 활용 패턴을 서술한다. 버전 목록이 아니라 "이 기술을 이 프로젝트에서는 이렇게 쓴다"를 설명한다.

포함 내용:
1. 핵심 기술 스택과 선택 이유 (uv 모노레포, pyrefly, ruff, pytest, commitizen 등)
2. 외부 라이브러리(FastAPI, SQLAlchemy, RabbitMQ/aio-pika, Kafka, Celery, OpenTelemetry, gRPC 등) 사용 패턴 — 어떤 플러그인에서 어떤 기능을 가져다 쓰는지
3. 의존성 관리 규칙 (`.claude/rules/dependencies.md` 요약: PyPI 버전 조회, 내부 의존성 워크스페이스 표기)
4. ADR로 분리된 결정은 ADR을 가리킨다 (중복 서술 금지)

### infrastructure / 런타임 토폴로지

> "외부 시스템과 어떻게 연결되어 있지?"

**소스**: 각 플러그인의 `Settings`/`Configuration`, 어댑터 구현체, 환경변수 사용처

> 본 프로젝트에는 단일 `infrastructure.md`가 없다. 인프라 서술은 각 플러그인 README와 `ARCHITECTURE.md` "런타임 통합" 섹션에 분산된다. 다중 플러그인이 하나의 외부 시스템을 공유하면 ARCHITECTURE.md에 통합 토폴로지를 둔다.

런타임 토폴로지를 서술한다. 애플리케이션이 외부 시스템과 실제로 어떻게 통신하는지를 종합한다.

포함 내용:
1. 시스템 컨텍스트 — Mermaid `flowchart`로 외부 시스템 연결 시각화 (DB, 메시지 브로커, 트레이서, 캐시 등)
2. SQLAlchemy: 사용 패턴, `SchemaRegistry`, 트랜잭션 경계, AggregateRoot 매핑
3. RabbitMQ / Kafka: 큐·exchange·topic 명명 규칙, 메시지 포맷, consume/publish 패턴
4. Outbox / Saga: 트랜잭션 경계와 relay 토폴로지
5. OpenTelemetry: 트레이서/메트릭 익스포터, span 명명 규약
6. 환경변수·설정 키 매핑 (`Settings` 클래스 기반)

### docs/guides/, docs/api/, docs/index.md, docs/glossary.md (사용자 문서)

> "프레임워크 사용자가 따라할 수 있는가?"

**소스**: 각 패키지 공개 API + 패키지 README

사용자 문서는 개발자 문서와 달리 **사용 시나리오 중심**으로 서술한다.

포함 내용:
1. 가이드: 1개 시나리오를 처음부터 끝까지 (설치 → 설정 → 실행 → 검증)
2. API 레퍼런스: 공개 시그니처, 파라미터, 반환, 예외 — autodoc과 중복되지 않는 사용 맥락 서술
3. 인덱스(`docs/index.md`): 패키지 테이블, 의존성 그래프, 튜토리얼 진입점 — `ARCHITECTURE.md`와 정합 필수
4. 용어집(`docs/glossary.md`): 사용자 관점 용어 정의 — 도메인 사전과 정합 필수

---

## Verifier 10항목 fact-check 체크리스트

Verifier는 다음 10항목을 빠짐없이 순회한다. 항목별로 검증 결과(이슈 N건 또는 "이슈 없음")를 보고한다.

1. **Mermaid 강제**: 문서 내 모든 시각화가 Mermaid인가? ASCII art / 텍스트 박스 / 유니코드 선 그림 발견 시 **Critical**.
2. **import 경로 정확성**: 문서에 등장하는 모든 import 경로를 실제 `.py` 파일과 대조. 한 글자도 신뢰하지 않는다.
3. **클래스/함수 시그니처 정확성**: 시그니처(파라미터, 타입 어노테이션, 반환 타입, 데코레이터)를 실제 코드와 1:1 대조.
4. **데코레이터 파라미터 정확성**: `@Aspect`, `@Configuration`, `@Bean` 등의 파라미터를 코드와 대조.
5. **패키지·파일 경로 존재성**: 언급된 모든 경로가 실제로 존재하는가? `git ls-files`로 검증.
6. **의존 방향 정합**: 문서가 주장하는 의존 방향이 실제 `pyproject.toml`·import 그래프와 일치하는가? 단방향 위반·plugin → plugin 위반 발견 시 **Critical**.
7. **환경변수·설정 키 정합**: 문서에 등장하는 환경변수·`Settings` 필드가 실제 코드에 존재하는가?
8. **ADR status 정합**: `accepted` ADR이 코드에 반영되어 있는가? `deprecated` ADR이 코드에 잔존하는가?
9. **코드 존재·문서 부재 누락 감지**: 코드에는 존재하지만 문서에 누락된 공개 API·Port·Aspect·Plugin·Aggregate를 적극적으로 찾는다. 단순 "문서 일치"가 아니라 "문서 충분성"까지 검증.
10. **용어 일관성**: 문서 내 용어가 `CLAUDE.md` 프로젝트 특수 컨벤션·`ARCHITECTURE.md` 도메인 어휘·도메인 사전과 일치하는가? 미등록 용어 발견 시 Warning.

각 항목에 대해 "확인할 수 없으면 [미확인]으로 보고" 한다. "아마 맞을 것이다"로 넘어가지 않는다.
