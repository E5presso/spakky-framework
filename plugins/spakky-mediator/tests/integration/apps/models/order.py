"""Order aggregate root for testing event publishing flow."""

from typing import Self
from uuid import UUID

from spakky.core.common.mutability import immutable, mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractDomainEvent


@mutable
class Order(AbstractAggregateRoot[UUID]):
    """Order aggregate root for testing."""

    @immutable
    class Created(AbstractDomainEvent):
        """Event raised when an order is created."""

        order_id: UUID
        customer_name: str
        total_amount: float

    @immutable
    class ItemAdded(AbstractDomainEvent):
        """Event raised when an item is added to an order."""

        order_id: UUID
        item_name: str
        quantity: int

    @immutable
    class Cancelled(AbstractDomainEvent):
        """Event raised when an order is cancelled."""

        order_id: UUID
        reason: str

    customer_name: str
    """Customer who placed the order."""

    total_amount: float
    """Total order amount."""

    items: list[str]
    """List of item names."""

    @classmethod
    def next_id(cls) -> UUID:
        """Generate next unique identifier for Order.

        Returns:
            New UUID7 identifier.
        """
        return uuid7()

    def validate(self) -> None:
        """Validate order state."""
        return

    @classmethod
    def create(cls, customer_name: str, total_amount: float) -> Self:
        """Create a new order and emit Order.Created event.

        Args:
            customer_name: Name of the customer.
            total_amount: Total order amount.

        Returns:
            New Order instance with Order.Created event added.
        """
        order = cls(
            uid=cls.next_id(),
            customer_name=customer_name,
            total_amount=total_amount,
            items=[],
        )
        order.add_event(
            cls.Created(
                order_id=order.uid,
                customer_name=customer_name,
                total_amount=total_amount,
            )
        )
        return order

    def add_item(self, item_name: str, quantity: int) -> None:
        """Add an item to the order.

        Args:
            item_name: Name of the item.
            quantity: Quantity to add.
        """
        self.items.append(item_name)
        self.add_event(
            Order.ItemAdded(
                order_id=self.uid,
                item_name=item_name,
                quantity=quantity,
            )
        )

    def cancel(self, reason: str) -> None:
        """Cancel the order.

        Args:
            reason: Reason for cancellation.
        """
        self.add_event(
            Order.Cancelled(
                order_id=self.uid,
                reason=reason,
            )
        )
