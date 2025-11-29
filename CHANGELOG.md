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
