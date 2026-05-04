## v6.5.0 (2026-05-04)

### Feat

- require python 3.12
- **cache**: complete redis-backed cache operations

## v6.4.0 (2026-05-03)

### 기능 추가

- **plugins**: add Redis plugin to workspace configuration
- **autopilot**: add auto-merge functionality and enhance user query handling
- **redis**: add Redis cache backend plugin (#170)
- **cache**: add cache annotation aspects (#169)
- **cache**: add in-memory cache core (#153) (#168)
- **fastapi**: add actuator HTTP endpoints (#149)
- **typer**: add actuator CLI commands (#152)
- **actuator**: add core aggregation contracts (#156)
- add portable agent harness plugin with templates and installer
- **monitor-pr**: 외부 리뷰 봇 평가 완료 조건 추가 및 문서 수정
- **core**: add discovery manifest scan reuse (#145) (#160)
- 외부 리뷰 봇 지원 및 리뷰 가이드라인 추가
- **core**: instrument startup diagnostics pipeline (#159)
- **core**: add DI dependency diagnostics (#146) (#158)
- **spakky**: add startup diagnostics contract
- Make RabbitMQ queues durable in event consumers and transports
- Update skills and documentation structure
- add /audit-codebase skill for multi-expert parallel codebase audit
- README.md에 spakky-saga, spakky-grpc, spakky-logging, spakky-opentelemetry 패키지 추가
- **saga**: DI 통합, 구조화 로그, 최종 내보내기 (#94) (#114)
- **grpc**: 통합 테스트 + 버그 수정 + 사용자 문서 (#87) (#113)
- **saga**: retry, skip, parallel, and timeout (#93) (#112)
- add refactor-code skill for automated harness violation audit
- **grpc**: implement PostProcessors for dynamic service registration (#86) (#107)
- **saga**: implement saga execution engine with sequential execution & compensation (#92) (#106)
- **saga**: implement flow builder API (saga_flow, step, parallel) (#102)
- **saga**: add @Saga() stereotype & AbstractSaga base class (#103)
- **grpc**: add type mapping engine (#85) (#105)
- **grpc**: add error hierarchy and gRPC interceptors (#84) (#104)
- **saga**: define type system and domain models (#101)
- **grpc**: scaffold spakky-grpc package with @GrpcController, @rpc and ProtoField (#83) (#97)
- **saga**: scaffold spakky-saga package with error hierarchy (#96)
- add ADR-0007 for spakky-saga — 분산 트랜잭션 사가 오케스트레이션 코어 패키지

### 수정

- plugin extras metadata 검증
- pre-commit에서 harness rule 강제
- explicit ABC interface 강제
- **harness**: ignore informational Codecov monitor comments (#163)
- update monitoring and merging logic in process-ticket and related scripts
- python-version을 3.14에서 3.11로 변경 및 pyproject.toml에 새로운 패키지 추가
- **sqlalchemy**: add typed wrapper helpers to resolve cross-package TypeVar bad-return errors
- add missing name field to monitor-pr skill definition

### 리팩터링

- enforce harness rules across packages
- Update SKILL.md files to reference Codex standard locations
- Refactor documentation references from CLAUDE.md to AGENTS.md across multiple skills and phases
- Refactor skills to use Claude Wrapper and update documentation
- **harness**: evaluate-harness 본분 명시 + git 자율 실행 제약 제거 (#142)
- **settings**: enhance hooks for session management and tool usage
- **grpc**: migrate DTO layer to pydantic BaseModel + json_format bridge (#133)
- **grpc**: rewrite PostProcessor unit tests as behavior-based (#132)
- **domain**: IAsync*UseCase.run을 Awaitable 반환 시그니처로 정정 (#131)
- **sqlalchemy**: SchemaRegistry 메서드 TypeVar를 AggregateRootT bound로 정교화 (#130)
- enforce harness rules in domain/event/plugins
- enforce harness rules across plugins
- make aggregate id typing invariant
- enforce harness rules across core packages
- enforce harness rules across all packages

## v6.3.1 (2026-04-04)

### 수정

- **core**: cache method wrappers in ProxyFactory to avoid re-creation on each access

## v6.3.0 (2026-04-04)

### 기능 추가

- add opentelemetry to optional dependencies in pyproject.toml
- add spakky-tracing and spakky-opentelemetry to package options
- 스킬 Phase 전환 시 현재 Phase의 산출물이 존재하는지 확인하는 항목 추가
- **celery**: remove _HAS_TRACING pattern, use get_or_none() Optional DI (#75)
- SKILL.md에 --skip-approval 옵션 추가 및 관련 단계 설명 보강
- ILogContextBinder ABC 정의 및 LogContext 구현 연결 (#72)
- **core**: add get_or_none() method to IContainer and ApplicationContext (#71)
- sync-dev-docs 및 sync-user-docs 스킬 추가 및 문서 동기화 로직 구현
- add sync-docs skill for synchronizing documentation with code changes
- sync-dev-docs 및 sync-user-docs 서브 스킬 추가 및 문서 동기화 로직 개선
- add new skills for architecture decision records, impact analysis, dependency audit, investigation, and property testing
- SKILL.md에서 태스크 및 서브태스크의 맥락 전파 원칙과 작업 명세 정리 절차 추가
- .gitignore에서 claude worktrees 경로 수정 및 create_package.py에서 pyrefly 체크 명령어 수정, workspace에 opentelemetry 플러그인 추가
- SKILL.md 파일에 user-invocable 속성 추가
- add spakky-opentelemetry plugin — OTel SDK bridge (#53)
- **celery**: add trace context propagation to task dispatch and worker (#38) (#52)
- **kafka**: add trace context extraction to consumers (#37) (#51)
- 커밋 및 PR 생성 단계 자동화 및 포맷팅 선행 추가
- Update Python code rules and skills for Spakky Framework
- **rabbitmq**: add trace context extraction to consumers (#50)
- .gitignore에 .claude/worktrees 추가 - 메타 리뷰 관련 파일 무시
- 세션 자가 평가 기록 전략 개선 - 단일 rolling 파일로 fail 기록 및 3-strike 감지 로직 추가
- **fastapi**: add TracingMiddleware for W3C Trace Context propagation (#49)
- 프로젝트 상태 자동 갱신 스킬 추가 - GitHub Issue에 연결된 프로젝트의 Status 필드 갱신 기능
- 브랜치명 생성 규칙 간소화 - 간결한 설명 제거
- 프로젝트 상태 갱신 단계 추가 - 각 Phase에 상태 업데이트 명령어 포함
- 새로운 SKILL 추가 - 코드 변경 후 품질 검증 및 자가 평가 기능
- **event,outbox,tracing**: add headers to IEventTransport for trace propagation (#47)
- **tracing**: add spakky-tracing core package (#44)

### 수정

- 수정된 @Logging AOP Aspect를 @logged AOP Aspect로 변경
- SKILL.md에서 선행 이슈 관계 설정 방법을 개선하고, 이슈 본문 메타데이터 추가
- SKILL.md에서 에픽 용어를 마일스톤으로 수정하고, 작업 분해 및 이슈 생성 규칙을 명확히 함
- PR 상태 모니터링 로직 개선 및 리뷰 코멘트 감지 추가
- 서브에이전트를 활용한 세션 회고 및 평가 절차 개선
- 워크트리 생성 절차에서 source 브랜치 최신화 방법 수정 및 develop 기준으로 리셋 추가
- 수정된 .gitignore 파일에서 불필요한 항목 제거 및 주석 정리
- README.md를 원래 내용으로 복원

### 리팩터링

- **kafka**: remove _HAS_TRACING pattern, use Optional DI with get_or_none() (#77)
- **opentelemetry**: replace _HAS_LOGGING with ILogContextBinder Optional DI (#68) (#78)
- **kafka**: remove _HAS_TRACING pattern, use Optional DI with get_or_none() (#77)
- **rabbitmq**: replace _HAS_TRACING with static import and get_or_none() (#66) (#76)
- **fastapi**: replace _HAS_TRACING with get_or_none() Optional DI (#67) (#74)
- **sqlalchemy**: remove _HAS_OUTBOX pattern and make spakky-outbox a required dependency (#69) (#73)
- 스킬 이름 변경 및 폴더 구조 정리

## v6.2.0 (2026-03-17)

### 기능 추가

- **task**: Add `get_async()` to `AbstractTaskResult` and `CeleryTaskResult` (#40) (#41)

## v6.1.3 (2026-03-16)

### 수정

- index.md flowchart 업데이트 및 mkdocs.yml README 제외 수정

## v6.1.2 (2026-03-16)

### 수정

- site_url을 올바른 domain으로 수정

## v6.1.1 (2026-03-16)

### 수정

- mkdocs strict mode warning 해결

## v6.1.0 (2026-03-16)

### 기능 추가

- **workflow**: add additional package options for publishing
- **yaml**: add custom YAML tags for enhanced validation in workspace settings
- **logging**: rename Logging to Logged and introduce logged shoredhanded decorator for method logging
- add transactional decorator and update documentation for shorthand usage
- **logging**: extract spakky-logging into standalone core package
- **celery**: add spakky-celery plugin with AOP-based task dispatch (#30)
- **spakky-task**: add spakky-task core package (#29)

### 수정

- **settings**: remove unnecessary YAML validation setting from VS Code configuration
- allow Python YAML tags in check-yaml hook and VS Code
- **docs**: remove premature tracing/otel refs, fix outbox classification
- **deps**: reorder optional dependencies for clarity
- **deps**: add missing logging dependency

### 리팩터링

- **event**: remove DuplicateEventHandlerError and allow multiple handlers for the same event type
- merge outbox-sqlalchemy into sqlalchemy, promote outbox to core
- **logging**: move spakky-logging to plugins/, rename import path to spakky.plugins.logging

## v6.0.0 (2026-03-10)

### 호환성 파괴 변경

- AbstractTable no longer requires from_domain/to_domain methods.
Use AbstractMappableTable for tables that map to domain entities.
- IEventTransport.send / IAsyncEventTransport.send now take
(event_name: str, payload: bytes) instead of (event: AbstractIntegrationEvent).
- all Domain/Integration-specific event interfaces removed.

### 기능 추가

- Transactional Outbox plugin (spakky-outbox + spakky-outbox-sqlalchemy) (#24)
- 토큰 효율성 평가 섹션 추가 및 관련 문서 업데이트
- **harness**: promote harness-update to skill with knowledge
- **hooks**: auto-mark session start and use session scope
- **harness**: add scope options to harness-review.py
- **sqlalchemy**: integrate AggregateCollector in Repository save/delete operations
- **scripts**: parallelize pre-commit and pre-push hooks
- **spakky-sqlalchemy**: implement AbstractGenericRepository with composite PK support
- **spakky-data**: add IGenericRepository/IAsyncGenericRepository interfaces
- **all**: 개발 의존성에 typer-cli 추가
- **plugin.sqlalchemy**: session 정리 절차 누락 수정
- **core**: AOP를 위해 객체 멤버 탐색 시, property를 건드리지 않도록 로직 수정
- **plugin.sqalchemy**: SessionManager와 Transaction의 세션 관리 정책을 변경
- **plugin.sqlalchemy**: 비동기 모드 지원 플래그 추가
- **plugin.sqlalchemy**: SessionManager와 Transaction 의존성 추가
- **plugin.sqlalchemy**: 스키마 레지스트리 추가
- **core**: Tag 및 TagRegistry 개념 추가
- **core**: Definition 스코프 제거 (설계 일관성 문제)
- **plugin.sqlalchemy**: Table 어노테이션 기능 추가
- **plugin.sqlalchemy**: sqlalchemy 플러그인 구현 원복, 구조 재설계
- **plugin.sqlalchemy**: Table 어노테이션 적용 시, dataclass 데코레이터에 대한 유효성 검사 제거
- **sqlalchemy**: add type-safe relation resolver (Phase 2)
- **sqlalchemy**: add table-level constraint support for named unique/index
- **sqlalchemy**: integrate relationship extraction in Extractor
- Implement SQLAlchemy Metadata Extractor (Phase 1) (#18)
- dataclass 타입 프로토콜 추가, version 필드에 uuid7 적용
- **event**: Implement in-process DomainEventPublisher infrastructure (#7)
- Add TransactionalEventPublishingAspect for automatic domain event publishing (#6)
- **data**: Implement @Transactional aspect for declarative transaction management (#5)
- AggregateCollector Pod 정의
- 도메인 이벤트와 통합 이벤트 분리, ApplicationContext에 Context 정보 제어 인터페이스 추가

### 수정

- update python project paths to current directory in VSCode settings
- **harness**: git add -A 금지 규칙 적용 및 이벤트 네이밍 불일치 수정
- add explicit TEMPLATE.md read step to architecture-decision skill
- **codecov**: change require_ci_to_pass value from 'yes' to 'true'
- **spakky-sqlalchemy**: add unique test data to prevent parallel test collisions
- **scripts**: query terminal width from /dev/tty directly
- **scripts**: enable real-time output for Rich console
- **scripts**: use print instead of console.print for CI JSON output
- **ci**: use uv run for scripts in GitHub Actions workflows
- **scripts**: modularize common utilities into lib package
- **plugin.sqlalchemy**: 메타데이터 선언을 직접 사용하도록 변경
- **post_processor**: 불필요한 asyncio 임포트 제거
- **plugin.sqlalchemy**: 방어로직에 대한 테스트 커버리지 제외
- **plugin.sqlalchemy**: 정적 타입 검사 오류 수정
- 잘못된 참조 경로 수정
- **core**: 누락된 ABC 상속 추가

### 리팩터링

- **sqlalchemy**: split AbstractTable into base and mappable classes
- **harness**: compress behavioral-guidelines and tool-usage instructions for token efficiency (#22)
- **event**: unify event interfaces with EventBus/Transport abstraction
- **harness**: 크로스파일 중복 제거 및 토큰 효율 원칙 추가
- merge adr instruction into architecture-decision skill
- **agent**: mermaid 도구 추가
- **event**: update pointcut annotations for async and sync transaction handling
- **harness**: optimize token budget for all harness files
- **agent**: 정리된 도구 목록 및 문서 규칙 개선
- split agent instructions for smaller context window
- **agent**: update tools list in spakky-dev agent configuration
- **core**: replace Any with object in annotation.py
- **core,rabbitmq**: add explanatory comments to type: ignore
- **all**: 불필요한 선언 제거
- **core.domain**: 불필요한 코드 베이스 제거 및 마커 클래스 정의
- 불필요한 성능 저하 방지를 위해 deepcopy 호출 제거

### Perf

- **ci**: separate coverage job from test matrix

## v5.0.1 (2025-12-06)

### 수정

- **plugin.rabbitmq**: 잘못된 환경변수 문서 수정

## v5.0.0 (2025-12-06)

### 기능 추가

- **core**: 순환 참조 발생 시, 오류 표현 형식 개선
- **core.domain**: Entity mutation 발생 시, updated_at & version 필드를 자동으로 업데이트
- **core**: ApplicationContext.stop에 스레드 락 추가
- **plugin.security**: 플러그인 구조 템플릿 셋업
- ApplicationContext의 싱글톤 캐시 Thread lock 추가
- **all**: :rotating_light: spakky-domain 내의 이벤트, 영속성 관련 코드를 별도 코어 패키지로 분리
- 통합 네임스페이스 영역을 제공하도록 기존 패키지 구조 수정
- **core**: 인터페이스 선언을 Protocol 기반에서 ABC로 변경
- ddd와 event 패키지 분리

### 수정

- **all**: 잘못된 의존성 업데이트 수정
- **all**: Release CI 오류 수정
- **all**: import shortcut 경로 제공
- **core.domain**: 해쉬 생성 로직 수정
- ValueObject의 XOR 기반 해쉬 처리 수정
- **all**: 타입, 환경변수 관련 오류 수정
- **all**: 누락된 테스트 관련 설정 및 파일 이동 수정
- **spakky-data**: 테스트 디스커버리 및 커버리지 관련 설정 수정

### 리팩터링

- **core**: Pod 탐색 로직 최적화
- 테스트 코드 경로 수정

## v4.0.0 (2025-11-29)

### 기능 추가

- **core**: add ensure_importable function for sys.path management
- built-in aspect enable 메서드 제거
- Logger 의존성 주입 메커니즘 제거

### 수정

- **rabbitmq**: 관련 코드 원복 및 assertion 제거
- **rabbitmq**: 이벤트 핸들러의 스코프 수정
- **rabbitmq**: EventConsumer의 의존성 스코프를 Context로 변경

## v3.4.0 (2025-11-28)

### 기능 추가

- kafka 플러그인 추가
- RabbitMQ SSL 프로토콜 지원 추가
- kafka 플러그인 프로젝트 추가
- RabbitMQ 설정 환경변수 prefix를 상수로 관리
- RabbitMQ 설정을 환경변수에 바로 로드할 수 있도록 수정

### 수정

- **kafka**: 잘못된 코드 제거
- **kafka**: 누락된 커버리지 설정 복구
- **kafka**: 누락된 Test 의존성 추가

### 리팩터링

- RabbitMQ 플러그인 패키지 구조 리팩터
- **rabbitmq**: 내부 이벤트 ser/des을 pydantic의 TypeAdapter 기반 처리로 전환
- 이벤트 관련 에러 정의 지점을 core 프레임워크로 이전

## v3.3.3 (2025-11-27)

### 리팩터링

- simplify error classes and clean up type annotations

## v3.3.2 (2025-11-26)

### 수정

- **release**: create tag after uv.lock update to prevent detached tags

## v3.3.1 (2025-11-26)

### 수정

- standardize 'monorepo' spelling across codebase

## v3.3.0 (2025-11-26)

### 기능 추가

- **typer**: reset context before executing cli endpoints
- **security**: document signature refresh after claim mutation
- **rabbitmq**: clarify context reuse safeguards for consumers
- **fastapi**: guard context per request when wiring routes
- **core**: document implicit scan path resolution
- **rabbitmq**: Message 관련 데이터 유효성 검사 실패 시 raise Error 추가
- **typer**: Context 스코프 제어 로직 추가
- **rabbitmq**: Context 스코프 제어 로직 추가
- **fastapi**: Context 스코프 제어 지점을 미들웨어에서 endpoint 개시 시점으로 변경
- **fastapi**: FastAPI lifespan에 Application stop 로직 주입

### 수정

- **ci**: exclude metadata files from package change detection
- **ci**: extract only latest version section for changelog and release notes
- **typer**: remove test comment from docstring
- **security**: remove test comment from docstring
- **rabbitmq**: remove test comment from docstring
- **ci**: only bump packages with actual file changes
- **fastapi**: remove test comment from docstring
- **core**: remove test comment from __init__.py
- **ci**: use tomllib instead of toml for Python 3.11+ compatibility
- **typer**: prepare for release
- **security**: prepare for release
- **rabbitmq**: prepare for release
- **fastapi**: prepare for release
- **core**: add pyrefly search_path for scripts and prepare for release
- **typer**: remove test comment from __init__.py
- **security**: remove test comment from __init__.py
- **rabbitmq**: remove test comment from __init__.py
- **fastapi**: remove test comment from __init__.py
- **core**: remove test comment from __init__.py
- **typer**: trigger release test
- **security**: trigger release test
- **rabbitmq**: trigger release test
- **fastapi**: trigger release test
- **core**: trigger release test
- **rabbitmq**: Context 초기화 지점을 Consumer Pod에서 PostProcessor로 이동

### 리팩터링

- **ci**: improve release workflow with unified commits
- **ci**: extract release workflow shell scripts to Python modules
- **core**: add custom constructors to error classes for detailed messages
- **rabbitmq**: call super().__init__ in error classes
- **fastapi**: call super().__init__ in AbstractSpakkyFastAPIError
- **core**: remove __str__ from AbstractSpakkyFrameworkError and use message attribute in tests
