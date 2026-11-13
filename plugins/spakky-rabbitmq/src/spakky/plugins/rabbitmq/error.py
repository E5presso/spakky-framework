"""Errors raised by the RabbitMQ plugin."""

from abc import ABC

from spakky.auth import AuthRequirementProviderUnavailableError
from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.event.subscription import SubscriberName


class AbstractSpakkyRabbitMQError(AbstractSpakkyFrameworkError, ABC):
    """Base error for RabbitMQ plugin operations."""


class SubscriberExchangeRequiredError(AbstractSpakkyRabbitMQError):
    """Raised at startup when a named subscriber is used without an exchange.

    Every named subscriber owns a queue bound to the configured exchange so
    that each one receives its own copy of an event. The default exchange can
    only deliver a message to the single queue named by its routing key.
    """

    message = "Named RabbitMQ subscribers require exchange_name to be configured"
    subscriber: SubscriberName
    event_type: type

    def __init__(self, subscriber: SubscriberName, event_type: type) -> None:
        self.subscriber = subscriber
        self.event_type = event_type
        super().__init__()


class RabbitMQAuthRequeueError(AuthRequirementProviderUnavailableError):
    """Raised when the auth failure policy keeps a message unacknowledged.

    The delivery contract lets provider-unavailable errors leave the delivery
    so that the message is not acknowledged. A `nack_requeue` auth policy asks
    for exactly that, so it is signalled through the same error family.
    """

    message = "Auth failure policy requeues the RabbitMQ message"
