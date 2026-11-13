"""Advised (AOP-proxied) domain event handlers are still registered."""

from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod
from spakky.data.aspects.transactional import Transactional, TransactionalAspect
from spakky.data.persistency.transaction import AbstractTransaction
from spakky.domain.models.event import AbstractDomainEvent
from spakky.event.event_dispatcher import IEventDispatcher
from spakky.event.stereotype.event_handler import EventHandler, on_event

from spakky.plugins.mediator.mediator import AsyncEventMediator, EventMediator
from spakky.plugins.mediator.post_processor import EventHandlerRegistrationPostProcessor


@immutable
class StockReserved(AbstractDomainEvent):
    """Stock was reserved."""

    sku: str


def test_transactional_domain_handler_expect_registered_and_run_in_transaction() -> (
    None
):
    """@Transactional이 붙어 프록시가 된 도메인 처리기도 등록되고 트랜잭션 안에서 실행된다."""
    log: list[str] = []

    @Pod()
    class RecordingTransaction(AbstractTransaction):
        def initialize(self) -> None:
            log.append("begin")

        def dispose(self) -> None: ...

        def commit(self) -> None:
            log.append("commit")

        def rollback(self) -> None:
            log.append("rollback")

    @EventHandler()
    class StockHandler:
        @on_event(StockReserved)
        @Transactional()
        def reserve(self, event: StockReserved) -> None:
            log.append(f"reserve:{event.sku}")

    context = ApplicationContext()
    for pod in (
        RecordingTransaction,
        TransactionalAspect,
        EventMediator,
        AsyncEventMediator,
        EventHandlerRegistrationPostProcessor,
        StockHandler,
    ):
        context.add(pod)
    context.start()
    try:
        context.get(IEventDispatcher).dispatch(StockReserved(sku="sku-1"))
    finally:
        context.stop()

    assert log == ["begin", "reserve:sku-1", "commit"]
