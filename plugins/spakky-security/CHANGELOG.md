# Changelog

All notable changes to spakky-security will be documented in this file.

See [GitHub Releases](https://github.com/E5presso/spakky-framework/releases) for full release history.

## 3.1.3 (2025-11-26)

### Fix

- **ci**: use tomllib instead of toml for Python 3.11+ compatibility
- **typer**: prepare for release
- **security**: prepare for release
- **rabbitmq**: prepare for release
- **fastapi**: prepare for release
- **core**: add pyrefly search_path for scripts and prepare for release

### Refactor

- **ci**: improve release workflow with unified commits

## spakky-security-v3.1.2 (2025-11-26)

### Fix

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

### Refactor

- **ci**: extract release workflow shell scripts to Python modules

## spakky-security-v3.1.0 (2025-11-26)

### Feat

- **rabbitmq**: Message 관련 데이터 유효성 검사 실패 시 raise Error 추가
- **typer**: Context 스코프 제어 로직 추가
- **rabbitmq**: Context 스코프 제어 로직 추가
- **fastapi**: Context 스코프 제어 지점을 미들웨어에서 endpoint 개시 시점으로 변경
- **fastapi**: FastAPI lifespan에 Application stop 로직 주입

### Fix

- **rabbitmq**: Context 초기화 지점을 Consumer Pod에서 PostProcessor로 이동

### Refactor

- **core**: add custom constructors to error classes for detailed messages
- **rabbitmq**: call super().__init__ in error classes
- **fastapi**: call super().__init__ in AbstractSpakkyFastAPIError
- **core**: remove __str__ from AbstractSpakkyFrameworkError and use message attribute in tests

## spakky-security-v3.0.0 (2025-11-25)


