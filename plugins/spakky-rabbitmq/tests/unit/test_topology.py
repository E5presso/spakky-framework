"""Unit tests for subscriber queue naming."""

from spakky.plugins.rabbitmq.event.topology import RabbitMQSubscriptionQueues


def test_subscription_queues_unnamed_subscriber_expect_event_named_queue() -> None:
    """이름 없는 구독자는 이벤트 이름 그대로의 큐를 유지한다."""
    queues = RabbitMQSubscriptionQueues.of("OrderPlaced", None)

    assert queues.queue == "OrderPlaced"
    assert queues.retry_queue == "OrderPlaced.retry"
    assert queues.dead_letter_queue == "OrderPlaced.dlq"


def test_subscription_queues_named_subscriber_expect_own_queue_family() -> None:
    """이름 있는 구독자는 `<event>.<subscriber>` 큐와 거기서 파생된 대기·dlq 큐를 갖는다."""
    queues = RabbitMQSubscriptionQueues.of("OrderPlaced", "billing")

    assert queues.queue == "OrderPlaced.billing"
    assert queues.retry_queue == "OrderPlaced.billing.retry"
    assert queues.dead_letter_queue == "OrderPlaced.billing.dlq"
