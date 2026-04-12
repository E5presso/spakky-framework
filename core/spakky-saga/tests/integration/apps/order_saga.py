"""Sample @Saga() class used for DI integration tests."""

from dataclasses import replace
from uuid import UUID, uuid4

from spakky.core.common.mutability import immutable
from spakky.saga.base import AbstractSaga
from spakky.saga.data import AbstractSagaData
from spakky.saga.flow import SagaFlow, saga_flow
from spakky.saga.stereotype import Saga


@immutable
class OrderSagaData(AbstractSagaData):
    """Order saga business data."""

    order_id: UUID
    ticket_id: UUID | None = None


@Saga()
class CreateOrderSaga(AbstractSaga[OrderSagaData]):
    """샘플 사가: 티켓을 발급하여 OrderSagaData를 확장한다."""

    async def issue_ticket(self, data: OrderSagaData) -> OrderSagaData:
        """Issue a ticket for the order."""
        return replace(data, ticket_id=uuid4())

    def flow(self) -> SagaFlow[OrderSagaData]:
        """Define saga flow."""
        return saga_flow(self.issue_ticket)
