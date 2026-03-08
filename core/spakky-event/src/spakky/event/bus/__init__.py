"""Spakky Event Bus package.

This package provides the default EventBus implementation that delegates
to an EventTransport for actual message delivery.
"""

from spakky.event.bus.transport_event_bus import (
    AsyncDirectEventBus,
    DirectEventBus,
)

__all__ = [
    "AsyncDirectEventBus",
    "DirectEventBus",
]
