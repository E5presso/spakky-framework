# Spakky Data

> [Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 데이터 접근 레이어 추상화입니다.
> Repository와 transaction boundary를 application layer에서 backend-neutral하게 선언하도록 돕습니다.

## 설치

```bash
pip install spakky-data
```

## 주요 기능

- **Repository 패턴**: Aggregate 영속화를 위한 generic repository 인터페이스
- **트랜잭션 관리**: autocommit과 중첩 transaction(`Propagation.REQUIRED`/`REQUIRES_NEW`)을 지원하는 추상 transaction 클래스
- **External Proxy**: 데이터베이스가 아닌 외부 service/storage 데이터 접근용 proxy 패턴

> `spakky-data`는 core 추상화 패키지입니다. SQLAlchemy engine/session/table mapping
> 구현체가 필요하면 `spakky-sqlalchemy`를 함께 설치하세요.

## 공통 실행 모드 설정

`spakky.data.config.DataConfig`가 `SPAKKY_DATA__SUPPORT_ASYNC_MODE`를 읽습니다.
기본값은 `true`이며, `false`이면 Data는 동기 `TransactionalAspect`만 등록합니다.
SQLAlchemy 등 영속성 구현 플러그인도 같은 설정으로 비동기 Pod 등록을 제어합니다.
따라서 동기 전용 드라이버를 사용하는 앱은 비동기 transaction provider 없이 시작할 수 있습니다.
비동기 트랜잭션을 사용하는 앱은 이 값을 `true`로 두고 비동기 provider를 제공해야 합니다.

이전 `SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE`는 제거됐습니다. 기존 설정은
`SPAKKY_DATA__SUPPORT_ASYNC_MODE`로 변경하세요. 두 변수의 우선순위나 호환 별칭은 없습니다.

## 설계 원칙

### Repository는 영속화 전용

Repository는 **domain aggregate에 대한 CRUD operation만** 처리합니다.
`find_by_xxx`, `search_xxx` 같은 query method를 repository에 추가하지 마세요.

복잡한 query는 ORM/SQL을 사용해 **QueryUseCase**에서 직접 구현해야 합니다.
Query 관심사를 도메인 레이어 밖에 두어 도메인 오염을 방지합니다.

```python
# ❌ 잘못된 예: repository에 query 관심사 포함
class IUserRepository:
    def find_by_email(self, email: str) -> User | None: ...

# ✅ 올바른 예: QueryUseCase에서 직접 구현
@UseCase()
class FindUserByEmailUseCase(IAsyncQueryUseCase[FindUserByEmailQuery, UserDTO]):
    async def run(self, query: FindUserByEmailQuery) -> UserDTO:
        # ORM/SQL 직접 사용
        ...
```

### 외부 연동 Proxy와 Repository

| 관점 | Repository | External Proxy |
|--------|-----------|----------------|
| 목적 | Domain aggregate persistence | 외부 service data access |
| 대상 | Database(ORM 경유) | REST API, gRPC, legacy system |
| 연산 | CRUD(save, delete, get) | Read-only(get, range) |
| 도메인 | 내부 bounded context | 외부 service |

## 빠른 시작

### SQLAlchemy와 함께 쓰는 기본 흐름

사용자 애플리케이션에서 가장 흔한 구성은 `spakky-data`의 Repository/Transaction 계약을
`spakky-sqlalchemy` 구현체로 채우는 방식입니다.

```bash
pip install spakky-data spakky-sqlalchemy
```

```bash
export SPAKKY_SQLALCHEMY__CONNECTION_STRING="postgresql+psycopg://user:pass@localhost/app"
export SPAKKY_DATA__SUPPORT_ASYNC_MODE="true"
```

흐름은 다음 순서로 구성합니다.

1. `AbstractAggregateRoot` 기반 domain aggregate를 정의합니다.
2. `spakky.plugins.sqlalchemy.orm.table.AbstractMappableTable`과 `@Table(Domain)`으로
   ORM table을 매핑합니다.
3. `spakky.plugins.sqlalchemy.persistency.repository.AbstractAsyncGenericRepository`를
   상속한 `@Repository()` 구현체를 등록합니다.
4. `@UseCase()` 메서드에 `@Transactional()`을 붙이고 Repository를 호출합니다.
5. 복잡한 조회는 Repository에 query method를 추가하지 않고 QueryUseCase에서
   `AsyncSessionManager` 또는 `SessionManager`로 직접 SQLAlchemy query를 실행합니다.

전체 예제는 [데이터베이스 가이드](../../docs/guides/sqlalchemy.md)를 참고하세요.

### Repository 패턴

domain aggregate용 repository interface를 정의합니다.

```python
from abc import abstractmethod
from uuid import UUID

from spakky.data.persistency.repository import IAsyncGenericRepository
from spakky.domain.models.aggregate_root import AbstractAggregateRoot


class User(AbstractAggregateRoot[UUID]):
    name: str
    email: str


# Repository interface: CRUD only, query method 없음
class IUserRepository(IAsyncGenericRepository[User, UUID]):
    pass  # get, get_or_none, contains, range, save, save_all, delete, delete_all
```

### Transaction 관리

database operation에는 추상 transaction을 사용합니다. 직접 구현해야 하는 경우도 있지만,
SQLAlchemy를 쓴다면 `spakky-sqlalchemy`의 `Transaction` / `AsyncTransaction`이 이 계약을
이미 구현합니다.

```python
from spakky.data.persistency.transaction import AbstractAsyncTransaction


class SQLAlchemyTransaction(AbstractAsyncTransaction):
    def __init__(self, session_factory, autocommit: bool = True) -> None:
        super().__init__(autocommit)
        self.session_factory = session_factory
        self.session = None

    async def initialize(self) -> None:
        self.session = self.session_factory()

    async def dispose(self) -> None:
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
```

context manager로 사용할 수 있습니다.

```python
async with transaction:
    user = await repository.get(user_id)
    user.name = "New Name"
    await repository.save(user)
    # 성공 시 자동 commit, exception 발생 시 rollback
```

### 중첩 transaction (propagation)

`@Transactional()` 메서드가 다른 `@Transactional()` 메서드를 부르는 중첩 호출은
`Propagation`으로 동작을 정합니다. 주지 않으면 `Propagation.REQUIRED`입니다.

```python
from spakky.data.aspects.transactional import Propagation, Transactional


@Transactional()  # = Transactional(propagation=Propagation.REQUIRED)
async def place_order(self, command: PlaceOrder) -> None: ...


@Transactional(propagation=Propagation.REQUIRES_NEW)
async def record_audit(self, entry: AuditEntry) -> None: ...
```

| Propagation | 바깥 transaction이 없을 때 | 바깥 transaction이 있을 때 |
|-------------|---------------------------|---------------------------|
| `REQUIRED` (기본) | 새로 열고, 끝나면 commit하고 닫는다 | 바깥에 합쳐진다. 같은 session을 쓰고 commit·닫기는 가장 바깥이 한 번 한다 |
| `REQUIRES_NEW` | 새로 열고, 끝나면 commit하고 닫는다 | 바깥을 그대로 두고 새 transaction(새 연결)을 연다. 끝나면 그것만 commit·rollback하고 닫은 뒤 바깥으로 돌아간다 |

- 합쳐진 안쪽에서 예외가 메서드 밖으로 나가면 그 transaction은 "rollback만 가능"으로 표시됩니다.
  바깥이 예외를 잡고 정상으로 끝나도 commit하지 않고 rollback한 뒤 `TransactionRollbackOnlyError`를 냅니다.
  바깥까지 예외가 올라가면 원래 예외로 끝납니다.
- `REQUIRES_NEW` 안쪽은 바깥이 아직 commit하지 않은 변경을 보지 못하고, 바깥이 잠근 행을 쓰면 서로 기다릴 수 있습니다.
  연결을 두 개 쓰므로 connection pool 크기를 그만큼 고려해야 합니다.
- 읽기 전용 조회도 `REQUIRED`라면 바깥에 합쳐져 같은 session으로 바깥의 flush된 변경을 읽습니다.
- `autocommit=False`이면 가장 바깥도 commit하지 않습니다.
- transaction scope는 실행 context(`contextvars`)를 따라갑니다. `asyncio.gather`/`create_task`로 만든 자식 task나
  `copy_context()`·`asyncio.to_thread`로 넘긴 thread는 바깥 scope를 이어받습니다.
  - 자식의 `REQUIRED`는 바깥 physical transaction에 합쳐집니다. 자식이 예외로 끝나면 바깥이 그 예외를 삼켜도
    바깥은 rollback하고 `TransactionRollbackOnlyError`를 냅니다. 자식이 모은 aggregate도 바깥 buffer에 들어갑니다.
  - 자식의 `REQUIRES_NEW`는 자식 context에만 쌓입니다. 동시에 연 여러 `REQUIRES_NEW`는 서로의 session을 쓰거나 닫지 않습니다.
  - 합쳐진 자식들은 바깥과 같은 session을 씁니다. SQLAlchemy session은 동시 사용에 안전하지 않으므로
    같은 session으로 동시에 DB를 쓰려면 자식마다 `REQUIRES_NEW`를 쓰세요.
- 바깥보다 오래 사는 자식(기다리지 않고 띄운 `create_task`, 끝까지 기다리지 않는 thread)은 다음과 같이 동작합니다.
  - transaction은 commit 또는 rollback을 마친 그 순간(session을 닫기 전) "끝남"이 됩니다. 그 뒤에 자식이
    `@Transactional`을 시작하면 끝난 transaction에는 합치지 않습니다. 그 아래 아직 살아 있는 transaction이 있으면
    거기에 합치고, 없으면 자기 transaction을 새로 열어 commit합니다. 이때 자식의 쓰기(session)와 aggregate(buffer)는
    언제나 자식이 합친 그 transaction의 것이라서, 쓰기는 rollback됐는데 이벤트만 나가는 일이 없습니다.
  - 바깥이 끝나기 전에 자식이 이미 합쳐져 있었는데 바깥이 먼저 끝나면, 자식은 그 뒤 쓰기(session 조회)와
    aggregate 수집에서 `TransactionAlreadyFinishedError`를 받고, 그 scope가 끝날 때도 같은 오류를 냅니다.
    아래의 다른 transaction의 session으로 넘어가 쓰지 않으므로, 실패한 자식의 쓰기가 다른 transaction과 함께
    commit되지 않습니다. 바깥보다 오래 걸릴 수 있는 자식 작업은 `REQUIRES_NEW`로 두거나, 바깥이 끝나기 전에 기다리세요.

`AggregateCollector`는 physical transaction(가장 바깥 또는 `REQUIRES_NEW`)마다 수집 buffer를 따로 두고, 그 buffer를
transaction(`PhysicalTransaction`)에 묶습니다. `@Transactional`은 scope가 transaction을 열었는지 합쳤는지를
scope 자신(`current_frame.owner`)에게서 받아, 연 경우 buffer를 열고(`begin_transaction`), 합친 경우 합친 transaction의
buffer로 모읍니다(`join_transaction`). `@Transactional`은 physical transaction이 commit된 직후 그 buffer를 `drain_committed()`로 넘기고,
`spakky-event`의 이벤트 발행 Aspect가 이를 꺼내 도메인 이벤트를 발행합니다. 그래서 합쳐진 안쪽이 끝날 때는
발행하지 않고, 가장 바깥이 commit한 뒤에 한 번 발행합니다. `REQUIRES_NEW` 안쪽의 이벤트는 안쪽이 commit한 뒤에 발행됩니다.

`TransactionSynchronization`은 같은 physical transaction 단위로 after-commit 작업을 모읍니다. `@Transactional`은
transaction이 실제로 commit된 직후에만 그 작업을 돌리고, rollback·rollback-only·`autocommit=False`로 끝나면 버립니다.
프레임워크 내부 장치(예: `spakky-outbox`가 commit 뒤 릴레이를 깨우는 일)가 쓰며, 애플리케이션은 호출하지 않습니다.
작업 frame은 buffer처럼 그 `PhysicalTransaction`에 묶이고, Aspect가 buffer를 열고 합치는 같은 판정(scope의 owner 여부)으로
열고(`begin_transaction`) 합칩니다(`join_transaction` / `leave_transaction`). transaction 안에서 띄운 자식 task도 부모
transaction에 작업을 걸지만, 그 transaction이 끝난 뒤(`PhysicalTransaction.finished`)에는 `is_active`가 `False`이고 작업을 걸 수 없습니다.

직접 transaction을 다룰 때는 `scope()`로 propagation을 줄 수 있습니다. `async with transaction:`은 `scope(Propagation.REQUIRED)`와 같습니다.

```python
async with transaction.scope():
    async with transaction.scope(Propagation.REQUIRES_NEW):
        ...  # 별도 session, 별도 commit
```

`AbstractTransaction` / `AbstractAsyncTransaction`을 직접 구현한다면 자원(session 등)을 physical transaction에 묶습니다.

- `initialize()`: 바깥 transaction을 유지한 채 새 자원을 열어 `current_frame.transaction`(새 `PhysicalTransaction`)에 묶습니다.
- `join()` / `leave()`: `REQUIRED` scope가 진행 중인 transaction에 합칠 때와 나갈 때 불립니다. `current_frame.transaction`이
  합친 transaction이며, 안쪽이 이미 끝났다면 그 아래의 transaction일 수 있습니다. 기본 구현은 아무것도 하지 않습니다.
- `dispose()`: `initialize()`가 연 자원을 닫고 바깥으로 돌아갑니다. `finished`가 켜진 뒤에 불립니다.
- 자원은 요청 전체가 공유하는 상태가 아니라 `ContextVar` 같은 실행 context 지역 상태에 두어야 자식 task의
  `REQUIRES_NEW`가 다른 task의 자원을 바꾸지 않습니다.
- 지금 쓸 자원은 현재 scope가 속한 transaction의 자원입니다. 그 transaction이 `finished`이면 아래 자원으로 넘어가지 말고
  `TransactionAlreadyFinishedError`를 내야 합니다. `finished`는 commit·rollback 직후, `dispose()` 전에 켜집니다.

### 외부 연동 Proxy 패턴

Proxy 인터페이스로 데이터베이스가 아닌 **외부 서비스**에 접근합니다.
REST API, gRPC 서비스, legacy 시스템 등에 사용합니다.

```python
from spakky.data.external.proxy import ProxyModel, IAsyncGenericProxy


# 외부 payment service의 data model
class PaymentInfo(ProxyModel[str]):
    transaction_id: str
    amount: int
    status: str


# 외부 payment service용 proxy interface
class IPaymentProxy(IAsyncGenericProxy[PaymentInfo, str]):
    pass


# 구현체는 외부 API 호출
class PaymentServiceProxy(IPaymentProxy):
    async def get(self, proxy_id: str) -> PaymentInfo:
        response = await self._http_client.get(f"/payments/{proxy_id}")
        return PaymentInfo(...)
```

## API 레퍼런스

### 영속성

| 클래스 | 설명 |
|-------|-------------|
| `IGenericRepository` | 동기 generic repository interface |
| `IAsyncGenericRepository` | 비동기 generic repository interface |
| `AbstractTransaction` | context manager를 가진 동기 transaction |
| `AbstractAsyncTransaction` | context manager를 가진 비동기 transaction |
| `Propagation` | 중첩 transaction의 동작(`REQUIRED`, `REQUIRES_NEW`) |
| `AggregateCollector` | physical transaction 단위로 저장된 aggregate를 모으는 collector |
| `TransactionSynchronization` | physical transaction이 실제로 commit된 뒤에 돌릴 작업(`AfterCommitCallback`)을 모으는 framework 내부 장치 |
| `TransactionSynchronizationNotOpenError` | 열린 transaction 없이 after-commit 작업을 걸거나 닫으려 할 때 발생 |
| `EntityNotFoundError` | entity를 찾지 못했을 때 발생 |
| `EntityAlreadyExistsError` | 새 aggregate 저장이 이미 있는 유일 키와 부딪혔을 때 발생. `VersionConflictError`와 별개 |

### 외부 연동

| 클래스 | 설명 |
|-------|-------------|
| `ProxyModel` | 외부 service data model 기반 클래스 |
| `IGenericProxy` | 동기 proxy interface |
| `IAsyncGenericProxy` | 비동기 proxy interface |

### 에러

| 클래스 | 설명 |
|-------|-------------|
| `AbstractSpakkyPersistencyError` | persistency operation 기반 error |
| `TransactionRollbackOnlyError` | 안쪽 scope의 실패로 rollback만 가능해진 transaction을 바깥이 정상 종료하려 할 때 발생 |
| `TransactionAlreadyFinishedError` | 이미 commit·rollback된 transaction의 자원(session, aggregate buffer)을 쓰려 하거나, 합쳐진 scope(주로 자식 task·thread)가 끝나기 전에 그 transaction이 먼저 끝났을 때 발생 |
| `TransactionNotActiveError` | 열린 scope 없이 transaction scope를 닫으려 할 때 발생 |
| `AggregateBufferNotOpenError` | 열지 않은 collector buffer를 닫으려 할 때 발생 |
| `AbstractSpakkyExternalError` | 외부 service operation 기반 error |

## 관련 패키지

| 패키지 | 설명 |
|---------|-------------|
| `spakky-domain` | DDD building block(Entity, AggregateRoot, ValueObject) |
| `spakky-event` | Event publisher/consumer interface |

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License

### 수집 목록의 실행 격리

`AggregateCollector`의 수집 목록은 Python 실행 컨텍스트별로 분리됩니다. Singleton Repository나 Aspect가 동일한 collector를 주입받아도 동시 비동기 요청의 목록은 섞이지 않습니다. buffer를 열고 닫는 일은 `@Transactional` Aspect가, commit된 aggregate의 이벤트 발행은 `spakky-event`의 트랜잭션 이벤트 Aspect가 담당합니다.
