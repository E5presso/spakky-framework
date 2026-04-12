"""Sample @Saga() classes used for DI integration tests."""

from dataclasses import replace
from uuid import UUID, uuid4

from spakky.core.common.mutability import immutable
from spakky.saga.base import AbstractSaga, saga_step
from spakky.saga.data import AbstractSagaData
from spakky.saga.flow import SagaFlow
from spakky.saga.strategy import Compensate, ExponentialBackoff, Retry, Skip
from spakky.saga.stereotype import Saga


@immutable
class OrderSagaData(AbstractSagaData):
    """Order saga business data."""

    order_id: UUID
    ticket_id: UUID | None = None
    payment_id: UUID | None = None
    shipment_id: UUID | None = None
    notifications_sent: int = 0


@Saga()
class CreateOrderSaga(AbstractSaga[OrderSagaData]):
    """복합 사가: 보상 쌍, 병렬 그룹, 에러 전략을 조합한 E2E 시나리오."""

    @saga_step
    async def issue_ticket(self, data: OrderSagaData) -> OrderSagaData:
        """티켓을 발급한다."""
        return replace(data, ticket_id=uuid4())

    @saga_step
    async def cancel_ticket(self, data: OrderSagaData) -> None:
        """발급된 티켓을 취소한다 (보상)."""

    @saga_step
    async def charge_payment(self, data: OrderSagaData) -> OrderSagaData:
        """결제를 청구한다."""
        return replace(data, payment_id=uuid4())

    @saga_step
    async def refund_payment(self, data: OrderSagaData) -> None:
        """결제를 환불한다 (보상)."""

    @saga_step
    async def notify_customer(self, data: OrderSagaData) -> OrderSagaData:
        """고객에게 알림을 전송한다 (side-effect)."""
        return replace(data, notifications_sent=data.notifications_sent + 1)

    @saga_step
    async def log_audit(self, data: OrderSagaData) -> OrderSagaData:
        """감사 로그를 기록한다 (side-effect)."""
        return replace(data, notifications_sent=data.notifications_sent + 1)

    @saga_step
    async def arrange_shipment(self, data: OrderSagaData) -> OrderSagaData:
        """배송을 수배한다."""
        return replace(data, shipment_id=uuid4())

    def flow(self) -> SagaFlow[OrderSagaData]:
        """Define the full saga flow."""
        retry_strategy = Retry(
            max_attempts=3,
            backoff=ExponentialBackoff(base=0.0),
            then=Compensate(),
        )
        return SagaFlow(
            items=(
                self.issue_ticket >> self.cancel_ticket,
                self.charge_payment >> self.refund_payment,
                self.notify_customer & self.log_audit,
                self.arrange_shipment | retry_strategy,
            ),
        )


@Saga()
class FailingOrderSaga(AbstractSaga[OrderSagaData]):
    """실패 경로 사가: 보상 체인과 Skip 전략을 혼합한 시나리오."""

    @saga_step
    async def issue_ticket(self, data: OrderSagaData) -> OrderSagaData:
        """티켓을 발급한다."""
        return replace(data, ticket_id=uuid4())

    @saga_step
    async def cancel_ticket(self, data: OrderSagaData) -> None:
        """발급된 티켓을 취소한다 (보상)."""

    @saga_step
    async def unreliable_step(self, data: OrderSagaData) -> None:
        """실패하지만 Skip 전략으로 무시되는 step."""
        raise RuntimeError("unreliable transient failure")

    @saga_step
    async def always_fail(self, data: OrderSagaData) -> None:
        """항상 실패하는 최종 step — 보상 체인을 유발한다."""
        raise RuntimeError("terminal failure")

    def flow(self) -> SagaFlow[OrderSagaData]:
        """Define the failing saga flow."""
        return SagaFlow(
            items=(
                self.issue_ticket >> self.cancel_ticket,
                self.unreliable_step | Skip(),
                self.always_fail,
            ),
        )
