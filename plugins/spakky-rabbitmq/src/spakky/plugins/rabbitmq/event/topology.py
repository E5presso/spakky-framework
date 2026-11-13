"""Names of the RabbitMQ queues one subscriber owns for one event."""

from typing import Self

from pydantic import BaseModel, ConfigDict
from spakky.event.subscription import SubscriberName

from spakky.plugins.rabbitmq.common.constants import (
    DEAD_LETTER_QUEUE_SUFFIX,
    RETRY_QUEUE_SUFFIX,
    SUBSCRIBER_QUEUE_SEPARATOR,
)

type EventName = str
"""Routing identity of an event; also the routing key it is published with."""

type QueueName = str
"""Name of a RabbitMQ queue."""


class RabbitMQSubscriptionQueues(BaseModel):
    """Queues that keep one subscriber's messages apart from every other one."""

    model_config = ConfigDict(frozen=True)

    queue: QueueName
    """Queue the subscriber consumes; bound to the exchange by the event name."""

    retry_queue: QueueName
    """Wait queue whose expired messages return to `queue` only."""

    dead_letter_queue: QueueName
    """Queue storing the messages the subscriber gave up on."""

    @classmethod
    def of(cls, event_name: EventName, subscriber: SubscriberName | None) -> Self:
        """Derive the queue names of `subscriber` for `event_name`.

        Args:
            event_name: Routing identity of the event.
            subscriber: Subscriber name; None is the unnamed subscriber, which
                keeps the queue named after the event alone.
        """
        queue = (
            event_name
            if subscriber is None
            else f"{event_name}{SUBSCRIBER_QUEUE_SEPARATOR}{subscriber}"
        )
        return cls(
            queue=queue,
            retry_queue=f"{queue}{RETRY_QUEUE_SUFFIX}",
            dead_letter_queue=f"{queue}{DEAD_LETTER_QUEUE_SUFFIX}",
        )
