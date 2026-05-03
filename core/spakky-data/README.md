# Spakky Data

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 데이터 접근 레이어 추상화입니다.

## 설치

```bash
pip install spakky-data
```

## 주요 기능

- **Repository 패턴**: Aggregate 영속화를 위한 generic repository 인터페이스
- **트랜잭션 관리**: autocommit을 지원하는 추상 transaction 클래스
- **External Proxy**: 데이터베이스가 아닌 외부 service/storage 데이터 접근용 proxy 패턴

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

database operation에는 추상 transaction을 사용합니다.

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
| `EntityNotFoundError` | entity를 찾지 못했을 때 발생 |

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
| `AbstractSpakkyExternalError` | 외부 service operation 기반 error |

## 관련 패키지

| 패키지 | 설명 |
|---------|-------------|
| `spakky-domain` | DDD building block(Entity, AggregateRoot, ValueObject) |
| `spakky-event` | Event publisher/consumer interface |

## 라이선스

MIT License
