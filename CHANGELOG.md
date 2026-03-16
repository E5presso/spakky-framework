## v6.1.3 (2026-03-16)

### Fix

- update flowchart in index.md and fix README exclusion in mkdocs.yml

## v6.1.2 (2026-03-16)

### Fix

- update site_url to the correct domain

## v6.1.1 (2026-03-16)

### Fix

- resolve mkdocs strict mode warnings

## v6.1.0 (2026-03-16)

### Feat

- **workflow**: add additional package options for publishing
- **yaml**: add custom YAML tags for enhanced validation in workspace settings
- **logging**: rename Logging to Logged and introduce logged shoredhanded decorator for method logging
- add transactional decorator and update documentation for shorthand usage
- **logging**: extract spakky-logging into standalone core package
- **celery**: add spakky-celery plugin with AOP-based task dispatch (#30)
- **spakky-task**: add spakky-task core package (#29)

### Fix

- **settings**: remove unnecessary YAML validation setting from VS Code configuration
- allow Python YAML tags in check-yaml hook and VS Code
- **docs**: remove premature tracing/otel refs, fix outbox classification
- **deps**: reorder optional dependencies for clarity
- **deps**: add missing logging dependency

### Refactor

- **event**: remove DuplicateEventHandlerError and allow multiple handlers for the same event type
- merge outbox-sqlalchemy into sqlalchemy, promote outbox to core
- **logging**: move spakky-logging to plugins/, rename import path to spakky.plugins.logging

## v6.0.0 (2026-03-10)

### BREAKING CHANGE

- AbstractTable no longer requires from_domain/to_domain methods.
Use AbstractMappableTable for tables that map to domain entities.
- IEventTransport.send / IAsyncEventTransport.send now take
(event_name: str, payload: bytes) instead of (event: AbstractIntegrationEvent).
- all Domain/Integration-specific event interfaces removed.

### Feat

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

### Fix

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

### Refactor

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

### Fix

- **plugin.rabbitmq**: 잘못된 환경변수 문서 수정

## v5.0.0 (2025-12-06)

### Feat

- **core**: 순환 참조 발생 시, 오류 표현 형식 개선
- **core.domain**: Entity mutation 발생 시, updated_at & version 필드를 자동으로 업데이트
- **core**: ApplicationContext.stop에 스레드 락 추가
- **plugin.security**: 플러그인 구조 템플릿 셋업
- ApplicationContext의 싱글톤 캐시 Thread lock 추가
- **all**: :rotating_light: spakky-domain 내의 이벤트, 영속성 관련 코드를 별도 코어 패키지로 분리
- 통합 네임스페이스 영역을 제공하도록 기존 패키지 구조 수정
- **core**: 인터페이스 선언을 Protocol 기반에서 ABC로 변경
- ddd와 event 패키지 분리

### Fix

- **all**: 잘못된 의존성 업데이트 수정
- **all**: Release CI 오류 수정
- **all**: import shortcut 경로 제공
- **core.domain**: 해쉬 생성 로직 수정
- ValueObject의 XOR 기반 해쉬 처리 수정
- **all**: 타입, 환경변수 관련 오류 수정
- **all**: 누락된 테스트 관련 설정 및 파일 이동 수정
- **spakky-data**: 테스트 디스커버리 및 커버리지 관련 설정 수정

### Refactor

- **core**: Pod 탐색 로직 최적화
- 테스트 코드 경로 수정

## v4.0.0 (2025-11-29)

### Feat

- **core**: add ensure_importable function for sys.path management
- built-in aspect enable 메서드 제거
- Logger 의존성 주입 메커니즘 제거

### Fix

- **rabbitmq**: 관련 코드 원복 및 assertion 제거
- **rabbitmq**: 이벤트 핸들러의 스코프 수정
- **rabbitmq**: EventConsumer의 의존성 스코프를 Context로 변경

## v3.4.0 (2025-11-28)

### Feat

- kafka 플러그인 추가
- RabbitMQ SSL 프로토콜 지원 추가
- kafka 플러그인 프로젝트 추가
- RabbitMQ 설정 환경변수 prefix를 상수로 관리
- RabbitMQ 설정을 환경변수에 바로 로드할 수 있도록 수정

### Fix

- **kafka**: 잘못된 코드 제거
- **kafka**: 누락된 커버리지 설정 복구
- **kafka**: 누락된 Test 의존성 추가

### Refactor

- RabbitMQ 플러그인 패키지 구조 리팩터
- **rabbitmq**: 내부 이벤트 ser/des을 pydantic의 TypeAdapter 기반 처리로 전환
- 이벤트 관련 에러 정의 지점을 core 프레임워크로 이전

## v3.3.3 (2025-11-27)

### Refactor

- simplify error classes and clean up type annotations

## v3.3.2 (2025-11-26)

### Fix

- **release**: create tag after uv.lock update to prevent detached tags

## v3.3.1 (2025-11-26)

### Fix

- standardize 'monorepo' spelling across codebase

## v3.3.0 (2025-11-26)

### Feat

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

### Fix

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

### Refactor

- **ci**: improve release workflow with unified commits
- **ci**: extract release workflow shell scripts to Python modules
- **core**: add custom constructors to error classes for detailed messages
- **rabbitmq**: call super().__init__ in error classes
- **fastapi**: call super().__init__ in AbstractSpakkyFastAPIError
- **core**: remove __str__ from AbstractSpakkyFrameworkError and use message attribute in tests
