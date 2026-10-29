"""Create order use cases for testing transactional event publishing."""

from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.aggregate_collector import AggregateCollector

from tests.integration.apps.models.order import Order


@UseCase()
class SyncCreateOrderUseCase:
    """Sync use case that creates an order and collects it."""

    _collector: AggregateCollector

    def __init__(self, collector: AggregateCollector) -> None:
        """Initialize use case with aggregate collector.

        Args:
            collector: Collector for tracking aggregates.
        """
        self._collector = collector

    @Transactional()
    def execute(self, customer_name: str, total_amount: float) -> Order:
        """Create an order within a transaction.

        Args:
            customer_name: Name of the customer.
            total_amount: Total order amount.

        Returns:
            Created Order instance.
        """
        order = Order.create(customer_name=customer_name, total_amount=total_amount)
        self._collector.collect(order)
        return order


@UseCase()
class AsyncCreateOrderUseCase:
    """Async use case that creates an order and collects it."""

    _collector: AggregateCollector

    def __init__(self, collector: AggregateCollector) -> None:
        """Initialize use case with aggregate collector.

        Args:
            collector: Collector for tracking aggregates.
        """
        self._collector = collector

    @Transactional()
    async def execute(self, customer_name: str, total_amount: float) -> Order:
        """Create an order within an async transaction.

        Args:
            customer_name: Name of the customer.
            total_amount: Total order amount.

        Returns:
            Created Order instance.
        """
        order = Order.create(customer_name=customer_name, total_amount=total_amount)
        self._collector.collect(order)
        return order


@UseCase()
class AsyncCreateOrderWithErrorUseCase:
    """Async use case that creates an order but raises an exception."""

    _collector: AggregateCollector

    def __init__(self, collector: AggregateCollector) -> None:
        """Initialize use case with aggregate collector.

        Args:
            collector: Collector for tracking aggregates.
        """
        self._collector = collector

    @Transactional()
    async def execute(self, customer_name: str, total_amount: float) -> Order:
        """Create an order but fail before completion.

        Args:
            customer_name: Name of the customer.
            total_amount: Total order amount.

        Returns:
            Never returns, always raises.

        Raises:
            RuntimeError: Always raised to simulate failure.
        """
        order = Order.create(customer_name=customer_name, total_amount=total_amount)
        self._collector.collect(order)
        raise RuntimeError("Transaction failed intentionally")


@UseCase()
class AsyncCreateOrderWithMultipleEventsUseCase:
    """Async use case that creates an order with multiple events."""

    _collector: AggregateCollector

    def __init__(self, collector: AggregateCollector) -> None:
        """Initialize use case with aggregate collector.

        Args:
            collector: Collector for tracking aggregates.
        """
        self._collector = collector

    @Transactional()
    async def execute(
        self,
        customer_name: str,
        total_amount: float,
        items: list[tuple[str, int]],
    ) -> Order:
        """Create an order with multiple items (multiple events).

        Args:
            customer_name: Name of the customer.
            total_amount: Total order amount.
            items: List of (item_name, quantity) tuples.

        Returns:
            Created Order instance with multiple events.
        """
        order = Order.create(customer_name=customer_name, total_amount=total_amount)
        for item_name, quantity in items:
            order.add_item(item_name, quantity)
        self._collector.collect(order)
        return order
