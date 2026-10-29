"""Opt-in local domain event provider registration."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.mediator.mediator import AsyncEventMediator, EventMediator
from spakky.plugins.mediator.post_processor import EventHandlerRegistrationPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Register only in-process domain consumer and dispatcher implementations.

    Args:
        app: Application selecting the optional mediator provider.
    """
    app.add(EventMediator)
    app.add(AsyncEventMediator)
    app.add(EventHandlerRegistrationPostProcessor)
