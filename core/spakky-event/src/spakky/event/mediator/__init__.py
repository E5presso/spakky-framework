"""Spakky Event Mediator package.

This package provides mediator implementations that combine Consumer and Dispatcher
interfaces for in-process event handling.
"""

from spakky.event.mediator.domain_event_mediator import (
    AsyncEventMediator,
    EventMediator,
)

__all__ = [
    "AsyncEventMediator",
    "EventMediator",
]
