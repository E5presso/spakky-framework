import pytest
from spakky.core.application.application import SpakkyApplication
from sqlalchemy import select

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.apps.models import User
from tests.apps.orm import UserTable


@pytest.mark.asyncio
async def test_transaction_commit_actual_model_changes(
    app: SpakkyApplication,
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction이 실제 모델 변경 사항을 커밋하는지 검증한다."""
    user = User.create(
        username="transactionuser",
        email="transactionuser@example.com",
        password_hash="transaction_hash_789",
    )

    async with async_transaction:
        user_table = schema_registry.from_domain(user)
        async_transaction.session.add(user_table)

    # 새 transaction에서 조회하여 커밋 검증
    new_transaction: AsyncTransaction = app.container.get(type_=AsyncTransaction)
    async with new_transaction:
        result = (
            await new_transaction.session.execute(
                select(UserTable).where(UserTable.uid == user.uid)
            )
        ).scalar_one_or_none()

        assert result is not None
        assert result.to_domain() == user


@pytest.mark.asyncio
async def test_transaction_rollback_on_exception(
    app: SpakkyApplication,
    schema_registry: SchemaRegistry,
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction이 예외 발생 시 롤백하는지 검증한다."""
    user = User.create(
        username="rollbackuser",
        email="rollbackuser@example.com",
        password_hash="rollback_hash_012",
    )

    with pytest.raises(Exception, match="Trigger rollback"):
        async with async_transaction:
            user_table = schema_registry.from_domain(user)
            async_transaction.session.add(user_table)
            raise Exception("Trigger rollback")

    # 새 transaction에서 조회하여 롤백 검증
    new_transaction: AsyncTransaction = app.container.get(type_=AsyncTransaction)
    async with new_transaction:
        result = (
            await new_transaction.session.execute(
                select(UserTable).where(UserTable.uid == user.uid)
            )
        ).scalar_one_or_none()

        assert result is None
