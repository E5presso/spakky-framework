<p align="center">
  <img src="./assets/symbol.svg" width="80rem" alt="Spakky Logo">
</p>
<h1 align="center">Spakky Framework</h1>
<p align="center"><i>DI와 AOP의 힘으로 확장 가능한 Python 애플리케이션을 만듭니다</i></p>

<p align="center">
  <a href="https://pypi.org/project/spakky/">
    <img src="https://img.shields.io/pypi/v/spakky.svg" alt="PyPI Version">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue" alt="Python Versions">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License">
  </a>
</p>

<h3 align="center">⚡️ 기반 도구</h3>
<p align="center">
  <a href="https://github.com/astral-sh/uv">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv">
  </a>
  <a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff">
  </a>
  <a href="https://github.com/facebook/pyrefly">
    <img src="https://img.shields.io/endpoint?url=https://pyrefly.org/badge.json" alt="Pyrefly">
  </a>
</p>

<h3 align="center">✅ CI 상태</h3>
<p align="center">
  <a href="https://github.com/E5presso/spakky-framework/actions/workflows/ci.yml">
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci.yml/badge.svg" alt="CI Status">
  </a>
  <a href="https://codecov.io/gh/E5presso/spakky-framework">
    <img src="https://codecov.io/gh/E5presso/spakky-framework/branch/develop/graph/badge.svg" alt="Codecov">
  </a>
</p>
</p>

<p align="center">
  <strong>문서</strong>: <a href="https://framework.spakky.com">https://framework.spakky.com</a>
</p>

---

**Spakky**는 확장 가능하고 모듈화된 애플리케이션을 쉽게 만들 수 있도록 설계된 현대적인 Spring-inspired Python 의존성 주입 프레임워크입니다. Inversion of Control(IoC)과 Aspect-Oriented Programming(AOP)을 Python 생태계에 맞게 제공하며 **FastAPI**, **RabbitMQ**, **Typer**를 일급으로 지원합니다.

## ✨ 주요 기능

- **의존성 주입(DI)**: `@Pod` 데코레이터를 사용하는 강력한 IoC 컨테이너이며 Singleton, Prototype, Context 스코프를 지원합니다.
- **관점 지향 프로그래밍(AOP)**: `@Aspect`, `@Before`, `@After`, `@Around`를 기본 제공하여 로깅과 트랜잭션 같은 횡단 관심사를 처리합니다.
- **모듈형 플러그인 시스템**: 주요 라이브러리를 플러그인으로 쉽게 확장할 수 있는 아키텍처.
- **타입 안전성**: 현대적인 Python 타입 힌트를 기준으로 설계되었습니다.
- **비동기 우선**: `asyncio`와 비동기 의존성 주입을 네이티브로 지원합니다.

## 📦 생태계

Spakky는 코어 프레임워크와 공식 플러그인을 함께 담은 모노레포입니다.

### 코어 패키지

| 패키지 | 설명 |
|---------|--------------|
| **`spakky`** | 코어 프레임워크(DI Container, AOP, Application Context) |
| **`spakky-domain`** | DDD 빌딩 블록(Entity, AggregateRoot, ValueObject, DomainEvent, CQRS) |
| **`spakky-data`** | 데이터 접근 추상화(Repository, Transaction, External Proxy) |
| **`spakky-event`** | 이벤트 처리(IEventPublisher, IEventBus, IEventTransport, @EventHandler) |
| **`spakky-task`** | 태스크 큐 추상화(@TaskHandler, @task, @schedule, Crontab) |
| **`spakky-agent`** | Agentic workflow core 계약(AgentExecutionSpec, AgentYield, AgentState/Signal/Evidence, IAgentModel) |
| **`spakky-actuator`** | 전송 계층 중립 health, readiness, liveness, info 계약 |
| **`spakky-cache`** | 백엔드 중립 애플리케이션 데이터 캐시 계약과 AOP 어노테이션 |
| **`spakky-tracing`** | 분산 트레이싱 추상화(TraceContext, ITracePropagator, W3C Propagator) |
| **`spakky-outbox`** | 신뢰할 수 있는 이벤트 전달을 위한 Transactional Outbox 패턴 |
| **`spakky-saga`** | 분산 트랜잭션 Saga 오케스트레이션(SagaFlow, SagaStep, 보상 처리) |

### 플러그인

| 패키지 | 설명 |
|---------|--------------|
| **`spakky-fastapi`** | REST API 구성을 위한 [FastAPI](https://fastapi.tiangolo.com/) 통합 |
| **`spakky-grpc`** | RPC 서비스 구성을 위한 [gRPC](https://grpc.io/) 통합 |
| **`spakky-kafka`** | [Apache Kafka](https://kafka.apache.org/) 기반 이벤트 주도 아키텍처 지원 |
| **`spakky-rabbitmq`** | [RabbitMQ](https://www.rabbitmq.com/) 기반 이벤트 주도 아키텍처 지원 |
| **`spakky-redis`** | 공유 애플리케이션 데이터 캐시를 위한 Redis 백엔드 |
| **`spakky-security`** | 보안 유틸리티(Cryptography, Password Hashing, JWT) |
| **`spakky-sqlalchemy`** | [SQLAlchemy](https://www.sqlalchemy.org/) ORM 데이터베이스 통합 |
| **`spakky-typer`** | [Typer](https://typer.tiangolo.com/) 기반 CLI 애플리케이션 지원 |
| **`spakky-vllm`** | 로컬 vLLM OpenAI-compatible endpoint를 위한 `IAgentModel` adapter |
| **`spakky-celery`** | AOP를 통한 [Celery](https://docs.celeryq.dev/) 태스크 디스패치와 스케줄 등록 |
| **`spakky-logging`** | `@logged` AOP aspect를 포함한 구조화 로깅 시스템 |
| **`spakky-opentelemetry`** | 분산 트레이싱을 위한 OpenTelemetry SDK 브릿지 |

## 🚀 빠른 시작

### 설치

코어 프레임워크를 설치합니다.

```bash
pip install spakky
```

플러그인을 함께 설치할 수도 있습니다.

```bash
pip install "spakky[fastapi,kafka]"
```

### 기본 사용법

`@Pod`로 서비스를 정의합니다.

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserRepository:
    def get_user(self, id: int) -> str:
        return "John Doe"

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_user_name(self, id: int) -> str:
        return self.repository.get_user(id)
```

애플리케이션을 부트스트랩합니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .scan()  # Auto-detects caller's package (works in Docker too!)
    .start()
)

user_service = app.container.get(UserService)
print(user_service.get_user_name(1))
```

> **📘 참고**: `scan()`을 인자 없이 호출하면 호출자의 패키지를 자동 감지해 스캔합니다. 애플리케이션 루트가 `sys.path`에 없을 수 있는 Docker 환경에서도 동작합니다.

## 🛠 개발

이 프로젝트는 의존성 관리와 workspace 처리를 위해 `uv`를 사용합니다.

### 사전 준비

- Python 3.12+
- `uv` 설치

### 설정

```bash
# 저장소 복제
git clone https://github.com/E5presso/spakky-framework.git
cd spakky-framework

# 의존성 동기화(workspace root에서 실행)
uv sync --all-packages --all-extras

# pre-commit hook 설치
uv run pre-commit install -t pre-commit -t commit-msg -t pre-push
```

> **💡 참고:** `--all-packages`는 workspace root에서만 사용하세요. 하위 패키지 내부에서 작업할 때는(예: `cd plugins/spakky-fastapi`) 대신 `uv sync --all-extras`를 사용합니다.

### 하위 프로젝트 독립 열기

각 하위 프로젝트는 VS Code에서 독립적으로 열 수 있습니다. 각 하위 프로젝트의 `.vscode/settings.json`는 루트 가상환경을 가리키므로 Python IntelliSense가 정상 동작합니다.

### 테스트 실행

```bash
cd core/spakky
uv run pytest

cd plugins/spakky-fastapi
uv run pytest

# 각 패키지에서 같은 방식으로 실행
```

## 🤝 기여

기여를 환영합니다. 자세한 내용은 [기여 가이드](CONTRIBUTING.md)를 참고하세요.

## 📄 라이선스

이 프로젝트는 MIT License로 배포됩니다.
