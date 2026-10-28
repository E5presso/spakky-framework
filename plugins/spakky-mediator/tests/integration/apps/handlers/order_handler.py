"""Order event handlers for testing event publishing flow."""

from spakky.event.stereotype.event_handler import EventHandler, on_event
from tests.integration.apps.handlers.event_recorder import EventRecorder
from tests.integration.apps.models.order import Order


@EventHandler()
class SyncOrderEventHandler:
    """Synchronous event handler for order events."""

    _recorder: EventRecorder

    def __init__(self, recorder: EventRecorder) -> None:
        """Initialize with event recorder.

        Args:
            recorder: Recorder to track handler invocations.
        """
        self._recorder = recorder

    @on_event(Order.Created)
    def on_order_created(self, event: Order.Created) -> None:
        """Handle Order.Created synchronously.

        Args:
            event: The order created event.
        """
        self._recorder.record("SyncOrderEventHandler.on_order_created", event)


@EventHandler()
class AsyncOrderEventHandler:
    """Asynchronous event handler for order events."""

    _recorder: EventRecorder

    def __init__(self, recorder: EventRecorder) -> None:
        """Initialize with event recorder.

        Args:
            recorder: Recorder to track handler invocations.
        """
        self._recorder = recorder

    @on_event(Order.Created)
    async def on_order_created(self, event: Order.Created) -> None:
        """Handle Order.Created asynchronously.

        Args:
            event: The order created event.
        """
        self._recorder.record("AsyncOrderEventHandler.on_order_created", event)

    @on_event(Order.ItemAdded)
    async def on_order_item_added(self, event: Order.ItemAdded) -> None:
        """Handle Order.ItemAdded asynchronously.

        Args:
            event: The order item added event.
        """
        self._recorder.record("AsyncOrderEventHandler.on_order_item_added", event)

    @on_event(Order.Cancelled)
    async def on_order_cancelled(self, event: Order.Cancelled) -> None:
        """Handle Order.Cancelled asynchronously.

        Args:
            event: The order cancelled event.
        """
        self._recorder.record("AsyncOrderEventHandler.on_order_cancelled", event)


@EventHandler()
class SecondAsyncOrderEventHandler:
    """Second async handler for testing multiple handlers for same event."""

    _recorder: EventRecorder

    def __init__(self, recorder: EventRecorder) -> None:
        """Initialize with event recorder.

        Args:
            recorder: Recorder to track handler invocations.
        """
        self._recorder = recorder

    @on_event(Order.Created)
    async def on_order_created(self, event: Order.Created) -> None:
        """Handle Order.Created (second handler).

        Args:
            event: The order created event.
        """
        self._recorder.record("SecondAsyncOrderEventHandler.on_order_created", event)


@EventHandler()
class FailingOrderEventHandler:
    """Handler that intentionally raises an exception."""

    _recorder: EventRecorder

    def __init__(self, recorder: EventRecorder) -> None:
        """Initialize with event recorder.

        Args:
            recorder: Recorder to track handler invocations.
        """
        self._recorder = recorder

    @on_event(Order.Created)
    async def on_order_created(self, event: Order.Created) -> None:
        """Handle Order.Created but fail.

        Args:
            event: The order created event.

        Raises:
            ValueError: Always raised to test resilient dispatch.
        """
        self._recorder.record("FailingOrderEventHandler.on_order_created", event)
        raise ValueError("Handler intentionally failed")
