RABBITMQ_CONFIG_ENV_PREFIX = "SPAKKY_RABBITMQ__"

SUBSCRIBER_QUEUE_SEPARATOR = "."
"""Separator between an event name and the subscriber that owns the queue."""

RETRY_QUEUE_SUFFIX = ".retry"
"""Suffix of the wait queue that holds a subscriber's delayed retries."""

DEAD_LETTER_QUEUE_SUFFIX = ".dlq"
"""Suffix of the queue that stores a subscriber's dead letters."""

DEFAULT_EXCHANGE_NAME = ""
"""AMQP default exchange: routes a message to the queue named by its routing key."""

DEAD_LETTER_EXCHANGE_ARGUMENT = "x-dead-letter-exchange"
"""Queue argument naming the exchange expired messages are republished to."""

DEAD_LETTER_ROUTING_KEY_ARGUMENT = "x-dead-letter-routing-key"
"""Queue argument naming the routing key expired messages are republished with."""

BLOCKING_PREFETCH_COUNT = 1
"""Unacknowledged messages allowed per queue while retries block the queue."""

PERSISTENT_DELIVERY_MODE = 2
"""AMQP delivery mode that survives a broker restart in a durable queue."""

MILLISECONDS_PER_SECOND = 1000
"""Factor between `RetryPolicy` seconds and AMQP expiration milliseconds."""
