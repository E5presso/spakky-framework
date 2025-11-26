## spakky-rabbitmq-v3.1.2 (2025-11-26)

### Fix

- **typer**: remove test comment from __init__.py
- **security**: remove test comment from __init__.py
- **rabbitmq**: remove test comment from __init__.py
- **fastapi**: remove test comment from __init__.py
- **core**: remove test comment from __init__.py

### Refactor

- **ci**: extract release workflow shell scripts to Python modules

## spakky-rabbitmq-v3.1.1 (2025-11-26)

### Fix

- **typer**: trigger release test
- **security**: trigger release test
- **rabbitmq**: trigger release test
- **fastapi**: trigger release test
- **core**: trigger release test

## spakky-rabbitmq-v3.1.0 (2025-11-26)

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

## spakky-rabbitmq-v3.0.0 (2025-11-25)
