from enum import StrEnum

SPAKKY_KAFKA_CONFIG_ENV_PREFIX = "SPAKKY_KAFKA__"


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
