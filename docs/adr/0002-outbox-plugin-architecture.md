# ADR-0002: Outbox 플러그인 아키텍처 — 추상화와 구현체 분리

- **상태**: Accepted
- **날짜**: 2026-03-10
- **관련**: [ADR-0001](0001-event-system-redesign.md) (Outbox Seam 정의)

## 맥락 (Context)

[ADR-0001](0001-event-system-redesign.md)에서 정의한 Outbox Seam을 기반으로 `spakky-outbox` 플러그인을 설계해야 한다.

초기 설계(GitHub Issue #4)는 `spakky-outbox`가 `spakky-sqlalchemy`에 직접 의존하는 구조였다:

```
spakky-outbox → spakky-sqlalchemy (하드 의존)
```

이 설계는 SQLAlchemy 외의 영속화 기술(MongoDB, DynamoDB 등)을 지원하지 못한다는 구조적 한계가 있다.

### 확장 요구사항

- **SQLAlchemy**: PostgreSQL, MySQL 등 관계형 DB (트랜잭션 원자성)
- **MongoDB**: 문서 DB (트랜잭션 지원, v4.0+)
- **DynamoDB**: AWS 서버리스 (TransactWriteItems API)
- **향후**: Redis Streams, Firestore 등

## 결정 동인 (Decision Drivers)

- **단일 책임**: Outbox 코어 로직과 영속화 구현을 분리
- **확장성**: 새 DB 지원 시 core 변경 없이 구현체만 추가
- **Opt-in 원칙**: Outbox 자체가 선택적 기능
- **코어 체인 보존**: `spakky → spakky-domain → spakky-data → spakky-event` 체인에 인프라 의존 추가 금지
- **Zero User Code**: 플러그인 설치만으로 동작

## 고려한 대안 (Considered Options)

### 대안 A: 추상화 + 구현체 분리 (채택)

`spakky-outbox`는 인터페이스와 코어 로직만 제공하고, `spakky-outbox-sqlalchemy` 등 구현체를 별도 패키지로 분리:

```
plugins/
├── spakky-outbox/                    # 추상화 (IOutboxStorage, Bus, Relay, Config)
├── spakky-outbox-sqlalchemy/         # SQLAlchemy 구현체
├── spakky-outbox-mongodb/            # MongoDB 구현체 (향후)
└── spakky-outbox-dynamodb/           # DynamoDB 구현체 (향후)
```

- **장점**: 단일 책임, 명확한 확장 포인트, 새 DB는 구현체만 추가
- **단점**: 패키지 수 증가 (2개 이상 설치 필요)

### 대안 B: 단일 플러그인 + 선택적 의존

`spakky-outbox` 하나가 모든 DB 구현을 포함하고, `extras_require`로 선택적 의존성 관리:

```python
# pyproject.toml
[project.optional-dependencies]
sqlalchemy = ["spakky-sqlalchemy>=0.0.1"]
mongodb = ["motor>=3.0"]
dynamodb = ["boto3>=1.28"]
```

설치: `pip install spakky-outbox[sqlalchemy]`

- **장점**: 단일 패키지, 설치 명령 단순
- **단점**: 코드 복잡도 증가, 불필요한 DB 코드 포함, 의존성 충돌 가능

### 대안 C: 각 인프라 플러그인에 Outbox 통합

`spakky-sqlalchemy`에 Outbox 기능을 직접 추가:

```
plugins/
├── spakky-sqlalchemy/               # + OutboxStorage, OutboxMessageTable
├── spakky-mongodb/                  # + OutboxStorage (향후)
```

- **장점**: 기존 플러그인 재사용
- **단점**: 책임 분리 위반 (SQLAlchemy 플러그인이 Event 시스템 알아야 함), `spakky-event` 의존 추가로 순환 가능성

## 결정 (Decision)

**대안 A를 채택한다.** 추상화와 구현체를 분리하여 확장성을 확보한다.

### 패키지 구조

```
plugins/
├── spakky-outbox/
│   └── src/spakky/plugins/outbox/
│       ├── __init__.py
│       ├── error.py
│       ├── main.py                   # initialize(app)
│       ├── common/
│       │   ├── config.py             # OutboxConfig
│       │   └── message.py            # OutboxMessage (dataclass)
│       ├── ports/
│       │   └── storage.py            # IOutboxStorage, IAsyncOutboxStorage
│       ├── bus/
│       │   └── outbox_event_bus.py   # AsyncOutboxEventBus (@Primary IAsyncEventBus)
│       └── relay/
│           └── relay.py              # OutboxRelay (IOutboxStorage → IAsyncEventTransport)
│
└── spakky-outbox-sqlalchemy/
    └── src/spakky/plugins/outbox_sqlalchemy/
        ├── __init__.py
        ├── main.py                   # initialize(app)
        ├── persistency/
        │   └── table.py              # OutboxBase, OutboxMessageTable
        └── adapters/
            └── storage.py            # SqlAlchemyOutboxStorage (@Primary IOutboxStorage)
```

### 핵심 인터페이스

```python
# spakky-outbox: common/message.py

@dataclass(frozen=True)
class OutboxMessage:
    """영속화 무관한 Outbox 메시지 모델."""
    id: UUID
    event_name: str      # topic/queue 라우팅 키
    payload: bytes       # JSON 직렬화된 이벤트
    created_at: datetime
    published_at: datetime | None = None
    retry_count: int = 0
    claimed_at: datetime | None = None  # atomic claim용


# spakky-outbox: ports/storage.py

class IOutboxStorage(ABC):
    """동기 Outbox 메시지 저장소 추상화."""

    @abstractmethod
    def save(self, message: OutboxMessage) -> None: ...
    @abstractmethod
    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]: ...
    @abstractmethod
    def mark_published(self, message_id: UUID) -> None: ...
    @abstractmethod
    def increment_retry(self, message_id: UUID) -> None: ...


class IAsyncOutboxStorage(ABC):
    """비동기 Outbox 메시지 저장소 추상화."""

    @abstractmethod
    async def save(self, message: OutboxMessage) -> None: ...
    @abstractmethod
    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]: ...
    @abstractmethod
    async def mark_published(self, message_id: UUID) -> None: ...
    @abstractmethod
    async def increment_retry(self, message_id: UUID) -> None: ...
```

### 의존성 그래프

```
spakky-event
     │
     ▼
spakky-outbox (IOutboxStorage, AsyncOutboxEventBus, OutboxRelay)
     │
     ├────────────────────────┬────────────────────────┐
     ▼                        ▼                        ▼
spakky-outbox-sqlalchemy  spakky-outbox-mongodb  spakky-outbox-dynamodb
     │                        │                        │
     ▼                        ▼                        ▼
spakky-sqlalchemy         motor (MongoDB)          boto3 (AWS)
```

### 이벤트 흐름

```
[Store Path — 같은 트랜잭션]
UseCase → AsyncEventPublisher
       → AsyncOutboxEventBus (@Primary IAsyncEventBus)
       → IOutboxStorage.save()
       → 비즈니스 데이터와 원자적 커밋

[Relay Path — 독립 세션]
OutboxRelay (BackgroundService)
       → IOutboxStorage.fetch_pending()
       → IAsyncEventTransport.send() (기존 Kafka/RabbitMQ)
       → IOutboxStorage.mark_published()
```

### 플러그인 위치: `plugins/`

Outbox는 opt-in 기능이며, 코어 체인(`spakky → spakky-domain → spakky-data → spakky-event`)에 속하지 않는다. `IAsyncEventBus`를 `@Primary`로 교체하는 확장이므로 `plugins/` 디렉토리가 적합하다.

## 결과 (Consequences)

### 긍정적

- **확장성**: 새 DB 지원 시 `spakky-outbox-*` 구현체만 추가
- **단일 책임**: Outbox 코어 로직과 영속화 구현 완전 분리
- **Zero Config**: 플러그인 2개 설치만으로 Outbox 활성화
- **테스트 용이**: `IOutboxStorage` mock으로 Bus/Relay 단위 테스트 가능

### 부정적

- **패키지 수 증가**: 사용자가 2개 이상 패키지 설치 필요 (`spakky-outbox` + `spakky-outbox-sqlalchemy`)
- **버전 호환성 관리**: 추상화와 구현체 간 버전 호환성 유지 필요

### 중립적

- **첫 버전 범위**: `spakky-outbox-sqlalchemy`만 구현, MongoDB/DynamoDB는 향후 별도 이슈

## 참고 자료

- [GitHub Issue #4: Create Transactional Outbox plugin](https://github.com/E5presso/spakky-framework/issues/4)
- [ADR-0001: 이벤트 시스템 재설계](0001-event-system-redesign.md)
- [Microsoft — Transactional Outbox Pattern](https://learn.microsoft.com/en-us/azure/architecture/best-practices/transactional-outbox-cosmos)
- [Chris Richardson — Pattern: Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html)
