"""Dummy integration events for outbox integration tests."""

from uuid import UUID

from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent


@immutable
class OrderConfirmedIntegrationEvent(AbstractIntegrationEvent):
    """Integration event fired when an order is confirmed."""

    order_id: UUID
