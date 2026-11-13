from enum import StrEnum

SPAKKY_KAFKA_CONFIG_ENV_PREFIX = "SPAKKY_KAFKA__"

REDRIVE_GROUP_SUFFIX = ".redrive"
"""Suffix of the consumer group that tracks a subscriber's redrive position."""

ASSIGNMENT_OFFSET_LOOKUP_TIMEOUT = 10.0
"""Seconds an assignment waits for the committed offsets of its retry partitions."""

type KafkaTopic = str
"""Name of a Kafka topic."""

type KafkaGroupId = str
"""Identifier of a Kafka consumer group."""


class DeadLetterHeaderKey(StrEnum):
    """Kafka header keys describing where a dead-lettered message came from.

    A reprocessing tool must be able to decide what to do from these headers
    alone, without parsing the original message body.
    """

    ORIGINAL_TOPIC = "x-spakky-dead-letter-original-topic"
    ORIGINAL_PARTITION = "x-spakky-dead-letter-original-partition"
    ORIGINAL_OFFSET = "x-spakky-dead-letter-original-offset"
    ORIGINAL_TIMESTAMP = "x-spakky-dead-letter-original-timestamp"
    CONSUMER_GROUP = "x-spakky-dead-letter-consumer-group"
    EXCEPTION_TYPE = "x-spakky-dead-letter-exception-type"
    EXCEPTION_MESSAGE = "x-spakky-dead-letter-exception-message"
