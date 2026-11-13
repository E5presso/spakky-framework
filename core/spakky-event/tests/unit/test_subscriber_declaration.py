"""Subscriber and handler-name declaration on the event handler stereotype."""

from unittest.mock import Mock

import pytest
from spakky.core.common.mutability import immutable
from spakky.core.pod.interfaces.container import IContainer
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.post_processor import EventHandlerProviderValidationPostProcessor
from spakky.event.stereotype.event_handler import EventHandler, EventRoute, on_event
from spakky.event.subscription import (
    InvalidSubscriberNameError,
    MixedSubscriptionModeError,
)


@immutable
class OrderPlaced(AbstractIntegrationEvent):
    """An order was placed."""

    order: str


def test_event_handler_subscriber_expect_declared_or_unnamed() -> None:
    """구독자 이름은 선언한 대로 읽히고, 없으면 이름 없는 구독자다."""

    @EventHandler(subscriber="billing")
    class Billing:
        @on_event(OrderPlaced)
        def charge(self, event: OrderPlaced) -> None: ...

    @EventHandler()
    class Legacy:
        @on_event(OrderPlaced, name="legacy-receive")
        def receive(self, event: OrderPlaced) -> None: ...

    assert EventHandler.get(Billing).subscriber == "billing"
    assert EventHandler.get(Legacy).subscriber is None
    assert (
        EventRoute.get(Billing.charge)
        .handler_name(Billing, "charge")
        .endswith("Billing.charge")
    )
    assert EventRoute.get(Legacy.receive).handler_name(Legacy, "receive") == (
        "legacy-receive"
    )


@pytest.mark.parametrize("name", ["", "bill.ing", "-billing", "a" * 64, "결제"])
def test_event_handler_invalid_subscriber_expect_rejected_at_declaration(
    name: str,
) -> None:
    """브로커 자원 이름이 될 수 없는 구독자 이름은 선언 시점에 거부된다."""
    with pytest.raises(InvalidSubscriberNameError):
        EventHandler(subscriber=name)


def test_mixed_sync_async_subscription_expect_startup_error() -> None:
    """한 구독에 동기·비동기 처리기가 섞이면 기동 시 오류다."""

    @EventHandler(subscriber="billing")
    class SyncBilling:
        @on_event(OrderPlaced)
        def charge(self, event: OrderPlaced) -> None: ...

    @EventHandler(subscriber="billing")
    class AsyncBilling:
        @on_event(OrderPlaced)
        async def notify(self, event: OrderPlaced) -> None: ...

    @EventHandler(subscriber="shipping")
    class AsyncShipping:
        @on_event(OrderPlaced)
        async def ship(self, event: OrderPlaced) -> None: ...

    registry = Mock(spec=IContainer)
    processor = EventHandlerProviderValidationPostProcessor()
    processor.set_container(registry)
    processor.post_process(SyncBilling())
    processor.post_process(AsyncShipping())
    with pytest.raises(MixedSubscriptionModeError) as caught:
        processor.post_process(AsyncBilling())
    assert (caught.value.subscriber, caught.value.event_type) == (
        "billing",
        OrderPlaced,
    )
