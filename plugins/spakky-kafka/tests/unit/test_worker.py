"""Unit tests for the per-subscriber Kafka workers.

Every scenario runs against the sync and the async worker through the harness
fixture, because both implement the same delivery contract.
"""

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from confluent_kafka import (
    OFFSET_BEGINNING,
    OFFSET_INVALID,
    KafkaError,
    KafkaException,
    TopicPartition,
)
from spakky.auth import (
    AuthRequirementDeniedError,
    AuthVerificationProviderUnavailableError,
)
from spakky.event.delivery import (
    DeadLetter,
    DeadLetterHeader,
    DeliveryHeader,
    DeliveryState,
    EventDeliveryContext,
    HandlerFailure,
    RetryMode,
    RetryPolicy,
)
from spakky.event.error import AbstractNonRetryableEventError, EventDeferredError
from spakky.event.redrive import RedriveResult
from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.kafka.auth import KAFKA_AUTH_HEADERS_PARAMETER
from spakky.plugins.kafka.common.config import (
    AutoOffsetResetType,
    KafkaConnectionConfig,
)
from spakky.plugins.kafka.common.constants import DeadLetterHeaderKey
from tests.unit.conftest import HarnessFactory
from tests.unit.harness import (
    SAMPLE_PAYLOAD,
    SAMPLE_SPAN_ID,
    SAMPLE_TRACE_ID,
    SAMPLE_TRACEPARENT,
    AnotherEvent,
    AsyncWorkerHarness,
    Clock,
    RenamedEvent,
    SampleEvent,
    SyncWorkerHarness,
    make_message,
)

ORIGIN = ("SampleEvent", 3, 42)
"""Coordinates of the default polled message."""

COMMITTED = ("SampleEvent", 3, 43)
"""Offset committed once the default polled message is settled."""


class PermanentFailure(AbstractNonRetryableEventError):
    """Failure another delivery attempt cannot fix."""

    message = "payload violates a business rule"


def fail(event: SampleEvent) -> None:
    """Handler body that always fails."""
    raise RuntimeError(f"cannot process {event.data}")


def dead_letter_headers(
    pending: tuple[str, ...] = ("first",), attempts: int = 1
) -> dict[str, str]:
    """Headers of a dead letter the unnamed subscriber stored for SampleEvent."""
    return {
        "x-custom": "kept",
        DeadLetterHeaderKey.ORIGINAL_TOPIC.value: "SampleEvent",
        DeadLetterHeaderKey.ORIGINAL_PARTITION.value: "3",
        DeadLetterHeaderKey.ORIGINAL_OFFSET.value: "42",
        DeadLetterHeaderKey.ORIGINAL_TIMESTAMP.value: "1700000000000",
        DeadLetterHeaderKey.CONSUMER_GROUP.value: "test-group",
        **DeadLetter(
            event_name="SampleEvent",
            subscriber=None,
            failures=tuple(
                HandlerFailure(
                    handler=handler,
                    exception_type="RuntimeError",
                    exception_message="boom",
                    retryable=True,
                )
                for handler in pending
            ),
            attempts=attempts,
            failed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ).to_headers(),
    }


def dead_letter(offset: int, headers: dict[str, str] | None = None) -> MagicMock:
    """A record stored on the unnamed subscriber's dead-letter topic."""
    return make_message(
        topic="SampleEvent.dlt",
        partition=0,
        offset=offset,
        headers=dead_letter_headers() if headers is None else headers,
    )


def test_worker_successful_handlers_expect_all_called_and_offset_committed(
    make_harness: HarnessFactory,
) -> None:
    """모든 핸들러가 성공하면 다음 오프셋을 커밋하고 아무것도 발행하지 않는다."""
    harness = make_harness()
    calls: list[str] = []
    harness.add("first", lambda event: calls.append(f"first:{event.data}"))
    harness.add("second", lambda event: calls.append(f"second:{event.data}"))

    harness.handle(make_message())

    assert calls == ["first:hello", "second:hello"]
    assert harness.committed() == [COMMITTED]
    assert harness.published() == []


def test_worker_custom_event_name_expect_routed_by_topic(
    make_harness: HarnessFactory,
) -> None:
    """event_name을 재정의한 이벤트는 그 토픽 이름으로 라우팅된다."""
    harness = make_harness()
    calls: list[str] = []
    harness.add("renamed", lambda event: calls.append(event.data), RenamedEvent)

    harness.handle(make_message(topic="external.renamed.v1"))

    assert calls == ["hello"]
    assert harness.worker_topics == (
        ["external.renamed.v1"],
        ["external.renamed.v1", "external.renamed.v1.dlt"],
    )


def test_worker_handler_runs_expect_delivery_context_of_its_subscriber(
    make_harness: HarnessFactory,
) -> None:
    """핸들러는 자기 구독자·핸들러 이름·시도 횟수가 담긴 전달 컨텍스트 안에서 실행된다."""
    harness = make_harness(subscriber="billing")
    seen: list[EventDeliveryContext] = []
    harness.add("charge", lambda event: seen.append(EventDeliveryContext.current()))

    harness.handle(make_message())

    assert [
        (context.subscriber, context.handler, context.attempt) for context in seen
    ] == [("billing", "charge", 1)]


def test_worker_broker_error_message_expect_logged_without_commit(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """브로커 오류 이벤트는 기록만 하고 핸들러 호출이나 커밋을 하지 않는다."""
    harness = make_harness()
    handler = MagicMock()
    harness.add("first", handler)
    message = make_message()
    message.error.return_value = KafkaError(KafkaError._PARTITION_EOF)

    with caplog.at_level(logging.ERROR):
        harness.handle(message)

    assert "Consumer error" in caplog.text
    handler.assert_not_called()
    assert harness.committed() == []


def test_worker_message_without_coordinates_expect_skipped(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """토픽·파티션·오프셋이 없는 메시지는 경고만 남기고 건너뛴다."""
    harness = make_harness()
    handler = MagicMock()
    harness.add("first", handler)
    message = make_message()
    message.offset.return_value = None

    with caplog.at_level(logging.WARNING):
        harness.handle(message)

    assert "no topic, partition or offset" in caplog.text
    handler.assert_not_called()
    assert harness.committed() == []


def test_worker_unknown_topic_expect_skipped_without_commit(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """등록되지 않은 토픽의 메시지는 커밋하지 않고 경고만 남긴다."""
    harness = make_harness()
    harness.add("first", MagicMock())

    with caplog.at_level(logging.WARNING):
        harness.handle(make_message(topic="Unregistered"))

    assert "unknown event type: Unregistered" in caplog.text
    assert harness.committed() == []


def test_worker_empty_body_expect_committed_without_dead_letter(
    make_harness: HarnessFactory,
) -> None:
    """본문 없는 메시지는 재시도해도 같으므로 dead-letter 없이 커밋한다."""
    harness = make_harness()
    handler = MagicMock()
    harness.add("first", handler)

    harness.handle(make_message(value=None))

    handler.assert_not_called()
    assert harness.committed() == [COMMITTED]
    assert harness.published() == []


def test_worker_undeserializable_body_expect_dead_letter_without_handler_or_retry(
    make_harness: HarnessFactory,
) -> None:
    """역직렬화할 수 없는 본문은 재시도 없이 모든 핸들러 이름과 함께 dead-letter로 간다."""
    harness = make_harness(RetryPolicy(max_attempts=5))
    handler = MagicMock()
    harness.add("first", handler)
    harness.add("second", MagicMock())

    harness.handle(make_message(value=b"not-json"))

    handler.assert_not_called()
    [record] = harness.published()
    assert record.topic == "SampleEvent.dlt"
    assert record.value == b"not-json"
    dead = DeadLetter.from_headers(record.headers)
    assert dead.attempts == 1
    assert [(failure.handler, failure.retryable) for failure in dead.failures] == [
        ("first", False),
        ("second", False),
    ]
    assert record.headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == "ValidationError"
    assert harness.committed() == [COMMITTED]


def test_worker_failing_handler_expect_dead_letter_with_origin_and_metadata(
    make_harness: HarnessFactory,
) -> None:
    """재시도가 없으면 실패한 메시지는 원본 본문·키·헤더와 메타데이터를 달고 DLT로 간다."""
    harness = make_harness()
    harness.add("first", fail)

    harness.handle(make_message(headers={"traceparent": SAMPLE_TRACEPARENT}))

    [record] = harness.published()
    assert record.topic == "SampleEvent.dlt"
    assert record.value == SAMPLE_PAYLOAD
    assert record.key == b"order-1"
    assert record.headers["traceparent"] == SAMPLE_TRACEPARENT
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == "SampleEvent"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_PARTITION] == "3"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "42"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_TIMESTAMP] == "1700000000000"
    assert record.headers[DeadLetterHeaderKey.CONSUMER_GROUP] == "test-group"
    assert record.headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == "RuntimeError"
    assert record.headers[DeadLetterHeaderKey.EXCEPTION_MESSAGE] == (
        "cannot process hello"
    )
    dead = DeadLetter.from_headers(record.headers)
    assert dead.event_name == "SampleEvent"
    assert dead.subscriber is None
    assert dead.attempts == 1
    assert dead.pending == frozenset({"first"})
    assert harness.committed() == [COMMITTED]


def test_worker_named_subscriber_failure_expect_own_dead_letter_topic_and_group(
    make_harness: HarnessFactory,
) -> None:
    """이름 있는 구독자는 자기 DLT와 자기 consumer group을 메타데이터에 남긴다."""
    harness = make_harness(subscriber="billing")
    harness.add("charge", fail)

    harness.handle(make_message())

    [record] = harness.published()
    assert record.topic == "SampleEvent.billing.dlt"
    assert record.headers[DeadLetterHeaderKey.CONSUMER_GROUP] == "test-group.billing"
    assert record.headers[DeadLetterHeader.SUBSCRIBER] == "billing"
    assert harness.worker_topics == (
        ["SampleEvent"],
        ["SampleEvent", "SampleEvent.billing.dlt"],
    )


def test_worker_blocking_retry_expect_partition_paused_and_only_failed_handler_rerun(
    make_harness: HarnessFactory, clock: Clock
) -> None:
    """제자리 재시도는 커밋 없이 파티션을 멈추고, 다시 올 때 실패한 핸들러만 실행한다."""
    harness = make_harness(RetryPolicy(max_attempts=3, initial_interval=5.0))
    calls: list[str] = []
    attempts: list[int] = []

    def flaky(event: SampleEvent) -> None:
        calls.append("flaky")
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise RuntimeError("first attempt fails")

    harness.add("flaky", flaky)
    harness.add("steady", lambda event: calls.append("steady"))

    harness.handle(make_message())

    assert calls == ["flaky", "steady"]
    assert harness.committed() == []
    assert harness.published() == []
    assert harness.paused() == [ORIGIN]
    assert harness.sought() == [ORIGIN]

    harness.resume_due()
    assert harness.resumed() == []
    clock.advance(5.0)
    harness.resume_due()
    assert harness.resumed() == [ORIGIN]

    harness.handle(make_message())

    assert calls == ["flaky", "steady", "flaky"]
    assert attempts == [1, 2]
    assert harness.committed() == [COMMITTED]
    assert harness.published() == []


def test_worker_blocking_retry_exhausted_expect_dead_letter_with_attempt_count(
    make_harness: HarnessFactory,
) -> None:
    """시도 횟수를 다 쓰면 그동안의 시도 횟수와 함께 dead-letter로 보낸다."""
    harness = make_harness(RetryPolicy(max_attempts=2))
    harness.add("first", fail)
    steady = MagicMock()
    harness.add("second", steady)

    harness.handle(make_message())
    harness.resume_due()
    harness.handle(make_message())

    steady.assert_called_once()
    [record] = harness.published()
    dead = DeadLetter.from_headers(record.headers)
    assert dead.attempts == 2
    assert dead.pending == frozenset({"first"})
    assert harness.committed() == [COMMITTED]


def test_worker_non_retryable_failure_expect_dead_letter_without_retry(
    make_harness: HarnessFactory,
) -> None:
    """재시도로 고칠 수 없는 실패는 남은 시도와 무관하게 바로 dead-letter로 간다."""
    harness = make_harness(RetryPolicy(max_attempts=5))

    def reject(event: SampleEvent) -> None:
        raise PermanentFailure()

    harness.add("first", reject)

    harness.handle(make_message())

    [record] = harness.published()
    dead = DeadLetter.from_headers(record.headers)
    assert dead.attempts == 1
    assert dead.failures[0].retryable is False
    assert harness.paused() == []
    assert harness.committed() == [COMMITTED]


def test_worker_deferred_handler_expect_wait_without_counting_attempt(
    make_harness: HarnessFactory, clock: Clock
) -> None:
    """지연 요청은 시도 횟수를 쓰지 않고 파티션을 멈춘 채 기다린다."""
    harness = make_harness()
    attempts: list[int] = []

    def gated(event: SampleEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise EventDeferredError(retry_after=7.0)
        raise RuntimeError("fails after the wait")

    harness.add("gated", gated)

    harness.handle(make_message())

    assert harness.committed() == []
    assert harness.published() == []
    assert harness.paused() == [ORIGIN]
    clock.advance(6.9)
    harness.resume_due()
    assert harness.resumed() == []
    clock.advance(0.1)
    harness.resume_due()
    assert harness.resumed() == [ORIGIN]

    harness.handle(make_message())

    assert attempts == [1, 1]
    [record] = harness.published()
    assert DeadLetter.from_headers(record.headers).attempts == 1


def test_worker_prefetched_record_on_waiting_partition_expect_ignored(
    make_harness: HarnessFactory,
) -> None:
    """멈춘 파티션에서 미리 가져온 뒤 레코드는 처리하지도 커밋하지도 않는다."""
    harness = make_harness(RetryPolicy(max_attempts=2, initial_interval=5.0))
    calls: list[str] = []

    def record_then_fail(event: SampleEvent) -> None:
        calls.append(event.data)
        raise RuntimeError("fails")

    harness.add("first", record_then_fail)
    harness.handle(make_message())

    harness.handle(make_message(offset=43))

    assert calls == ["hello"]
    assert harness.committed() == []


def test_worker_pause_rejected_expect_fence_kept(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """pause가 거절돼도 울타리는 남아 뒤 레코드가 앞질러 커밋되지 않는다."""
    harness = make_harness(RetryPolicy(max_attempts=2, initial_interval=5.0))
    handler = MagicMock(side_effect=RuntimeError("fails"))
    harness.add("first", handler)
    harness.consumer.pause.side_effect = KafkaException(KafkaError(KafkaError._STATE))

    with caplog.at_level(logging.WARNING):
        harness.handle(make_message())
    harness.handle(make_message(offset=43))

    assert "Cannot pause waiting partition" in caplog.text
    assert handler.call_count == 1
    assert harness.committed() == []


def test_worker_resume_rejected_expect_fence_kept_until_resume_succeeds(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """resume이 거절되면 울타리를 유지하고 다음 기회에 다시 시도한다."""
    harness = make_harness(RetryPolicy(max_attempts=2))
    handler = MagicMock(side_effect=RuntimeError("fails"))
    harness.add("first", handler)
    harness.handle(make_message())
    harness.consumer.resume.side_effect = KafkaException(KafkaError(KafkaError._STATE))

    with caplog.at_level(logging.WARNING):
        harness.resume_due()
    harness.handle(make_message())

    assert "Cannot resume waiting partition" in caplog.text
    assert handler.call_count == 1

    harness.consumer.resume.side_effect = None
    harness.resume_due()
    harness.handle(make_message())

    assert handler.call_count == 2


def test_worker_rebalance_expect_wait_and_retry_state_forgotten(
    make_harness: HarnessFactory,
) -> None:
    """파티션 소유권이 바뀌면 기억한 재시도 상태를 버리고 첫 시도로 다시 전달한다."""
    harness = make_harness(RetryPolicy(max_attempts=3, initial_interval=5.0))
    calls: list[str] = []

    def flaky(event: SampleEvent) -> None:
        calls.append("flaky")
        if calls.count("flaky") == 1:
            raise RuntimeError("first attempt fails")

    harness.add("flaky", flaky)
    harness.add("steady", lambda event: calls.append("steady"))
    harness.handle(make_message())

    harness.forget([TopicPartition("SampleEvent", 3)])
    harness.handle(make_message())

    assert calls == ["flaky", "steady", "flaky", "steady"]
    assert harness.committed() == [COMMITTED]


def test_worker_rebalance_of_other_partition_expect_retry_state_kept(
    make_harness: HarnessFactory, clock: Clock
) -> None:
    """다른 파티션의 재할당은 기다리는 메시지의 재시도 상태를 건드리지 않는다."""
    harness = make_harness(RetryPolicy(max_attempts=3, initial_interval=5.0))
    calls: list[str] = []

    def flaky(event: SampleEvent) -> None:
        calls.append("flaky")
        if calls.count("flaky") == 1:
            raise RuntimeError("first attempt fails")

    harness.add("flaky", flaky)
    harness.add("steady", lambda event: calls.append("steady"))
    harness.handle(make_message())

    harness.forget([TopicPartition("SampleEvent", 9)])
    harness.handle(make_message())
    clock.advance(5.0)
    harness.resume_due()
    harness.handle(make_message())

    assert calls == ["flaky", "steady", "flaky"]


def test_worker_assignment_latest_reset_expect_unread_retry_partition_from_beginning(
    make_harness: HarnessFactory, config: KafkaConnectionConfig
) -> None:
    """`latest` 정책에서도 커밋된 적 없는 retry 파티션은 처음부터 읽고 나머지는 그대로 둔다."""
    config.auto_offset_reset = AutoOffsetResetType.LATEST
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    harness.add("first", MagicMock())
    harness.consumer.committed.return_value = [
        TopicPartition("SampleEvent.retry", 0, OFFSET_INVALID),
        TopicPartition("SampleEvent.retry", 1, 7),
    ]
    event_partition = TopicPartition("SampleEvent", 0)
    read_partition = TopicPartition("SampleEvent.retry", 1)

    harness.assigned(
        [event_partition, TopicPartition("SampleEvent.retry", 0), read_partition]
    )

    looked_up = harness.consumer.committed.call_args.args[0]
    assert [(position.topic, position.partition) for position in looked_up] == [
        ("SampleEvent.retry", 0),
        ("SampleEvent.retry", 1),
    ]
    assignment = harness.consumer.assign.call_args.args[0]
    assert assignment[0] is event_partition
    assert (assignment[1].topic, assignment[1].partition, assignment[1].offset) == (
        "SampleEvent.retry",
        0,
        OFFSET_BEGINNING,
    )
    assert assignment[2] is read_partition


def test_worker_assignment_latest_reset_expect_committed_retry_partitions_untouched(
    make_harness: HarnessFactory, config: KafkaConnectionConfig
) -> None:
    """retry 파티션에 커밋된 위치가 있으면 기본 할당을 바꾸지 않는다."""
    config.auto_offset_reset = AutoOffsetResetType.LATEST
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    harness.add("first", MagicMock())
    harness.consumer.committed.return_value = [
        TopicPartition("SampleEvent.retry", 0, 3)
    ]

    harness.assigned([TopicPartition("SampleEvent.retry", 0)])

    harness.consumer.committed.assert_called_once()
    harness.consumer.assign.assert_not_called()


def test_worker_assignment_without_retry_partitions_expect_no_offset_lookup(
    make_harness: HarnessFactory, config: KafkaConnectionConfig
) -> None:
    """retry 파티션이 없는 할당은 커밋 위치를 조회하지 않고 사용자의 reset 정책을 따른다."""
    config.auto_offset_reset = AutoOffsetResetType.LATEST
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    harness.add("first", MagicMock())

    harness.assigned([TopicPartition("SampleEvent", 0)])

    harness.consumer.committed.assert_not_called()
    harness.consumer.assign.assert_not_called()


def test_worker_assignment_earliest_reset_expect_no_offset_lookup(
    make_harness: HarnessFactory,
) -> None:
    """`earliest` 정책은 이미 처음부터 읽으므로 retry 파티션도 따로 조회하지 않는다."""
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    harness.add("first", MagicMock())

    harness.assigned([TopicPartition("SampleEvent.retry", 0)])

    harness.consumer.committed.assert_not_called()
    harness.consumer.assign.assert_not_called()


def test_worker_assignment_offset_lookup_fails_expect_error_propagated_without_assign(
    make_harness: HarnessFactory, config: KafkaConnectionConfig
) -> None:
    """커밋 위치를 읽지 못하면 retry를 건너뛸 수 있는 할당을 하지 않고 오류를 전파한다."""
    config.auto_offset_reset = AutoOffsetResetType.NONE
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    harness.add("first", MagicMock())
    harness.consumer.committed.side_effect = KafkaException(
        KafkaError(KafkaError._TIMED_OUT)
    )

    with pytest.raises(KafkaException):
        harness.assigned([TopicPartition("SampleEvent.retry", 0)])

    harness.consumer.assign.assert_not_called()


def test_worker_assignment_expect_wait_and_retry_state_of_assigned_partition_forgotten(
    make_harness: HarnessFactory,
) -> None:
    """새로 할당받은 파티션의 이전 대기 상태는 버리고 첫 시도로 다시 전달한다."""
    harness = make_harness(RetryPolicy(max_attempts=3, initial_interval=5.0))
    handler = MagicMock(side_effect=RuntimeError("fails"))
    harness.add("first", handler)
    harness.handle(make_message())

    harness.assigned([TopicPartition("SampleEvent", 3)])
    harness.handle(make_message())

    assert handler.call_count == 2
    assert harness.published() == []


def test_worker_delayed_retry_expect_retry_record_published_and_offset_committed(
    make_harness: HarnessFactory,
) -> None:
    """DELAYED 재시도는 상태와 실행 가능 시각을 담아 retry 토픽에 발행한 뒤 커밋한다."""
    harness = make_harness(
        RetryPolicy(max_attempts=3, initial_interval=5.0, mode=RetryMode.DELAYED),
        subscriber="billing",
    )
    harness.add("charge", fail)
    harness.add("audit", MagicMock())

    harness.handle(make_message(headers={"x-custom": "kept"}))

    [record] = harness.published()
    assert record.topic == "SampleEvent.billing.retry"
    assert record.value == SAMPLE_PAYLOAD
    assert record.key == b"order-1"
    assert record.headers["x-custom"] == "kept"
    assert DeliveryState.from_headers(record.headers) == DeliveryState(
        attempt=2, pending=frozenset({"charge"})
    )
    assert record.headers[DeliveryHeader.NOT_BEFORE] == "1005.0"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == "SampleEvent"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "42"
    assert harness.committed() == [COMMITTED]
    assert harness.paused() == []
    assert harness.worker_topics == (
        ["SampleEvent", "SampleEvent.billing.retry"],
        ["SampleEvent", "SampleEvent.billing.retry", "SampleEvent.billing.dlt"],
    )


def test_worker_delayed_retry_publish_refused_expect_wait_in_place_without_commit(
    make_harness: HarnessFactory, clock: Clock
) -> None:
    """retry 레코드가 브로커에 닿지 않으면 커밋하지 않고 제자리에서 기다린다."""
    harness = make_harness(
        RetryPolicy(max_attempts=3, initial_interval=5.0, mode=RetryMode.DELAYED)
    )
    calls: list[str] = []

    def flaky(event: SampleEvent) -> None:
        calls.append("flaky")
        if calls.count("flaky") == 1:
            raise RuntimeError("first attempt fails")

    harness.add("flaky", flaky)
    harness.add("steady", lambda event: calls.append("steady"))
    harness.refuse_publish()

    harness.handle(make_message())

    assert harness.committed() == []
    assert harness.paused() == [ORIGIN]

    clock.advance(5.0)
    harness.resume_due()
    harness.handle(make_message())

    assert calls == ["flaky", "steady", "flaky"]
    assert harness.committed() == [COMMITTED]


def test_worker_retry_record_not_due_expect_partition_paused_until_due(
    make_harness: HarnessFactory, clock: Clock
) -> None:
    """아직 때가 안 된 retry 레코드는 시도 없이 그 파티션만 남은 시간 동안 멈춘다."""
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    handler = MagicMock()
    harness.add("first", handler)
    retry = make_message(
        topic="SampleEvent.retry",
        partition=0,
        offset=7,
        headers={
            **DeliveryState(attempt=2, pending=frozenset({"first"})).to_headers(),
            DeliveryHeader.NOT_BEFORE.value: "1004.0",
        },
    )

    harness.handle(retry)

    handler.assert_not_called()
    assert harness.committed() == []
    assert harness.paused() == [("SampleEvent.retry", 0, 7)]
    clock.advance(3.9)
    harness.resume_due()
    assert harness.resumed() == []
    clock.advance(0.1)
    harness.resume_due()
    assert harness.resumed() == [("SampleEvent.retry", 0, 7)]

    harness.handle(retry)

    handler.assert_called_once()
    assert harness.committed() == [("SampleEvent.retry", 0, 8)]


def test_worker_due_retry_record_expect_only_pending_handler_run_with_carried_attempt(
    make_harness: HarnessFactory,
) -> None:
    """때가 된 retry 레코드는 헤더의 상태대로 남은 핸들러만 그 시도 번호로 실행한다."""
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    attempts: list[int] = []
    steady = MagicMock()
    harness.add(
        "flaky", lambda event: attempts.append(EventDeliveryContext.current().attempt)
    )
    harness.add("steady", steady)

    harness.handle(
        make_message(
            topic="SampleEvent.retry",
            partition=0,
            offset=7,
            headers={
                **DeliveryState(attempt=2, pending=frozenset({"flaky"})).to_headers(),
                DeliveryHeader.NOT_BEFORE.value: "999.0",
            },
        )
    )

    assert attempts == [2]
    steady.assert_not_called()
    assert harness.committed() == [("SampleEvent.retry", 0, 8)]
    assert harness.published() == []


def test_worker_retry_record_exhausted_expect_dead_letter_with_original_coordinates(
    make_harness: HarnessFactory,
) -> None:
    """retry 토픽에서 시도를 다 쓴 레코드는 원본 좌표를 유지한 채 DLT로 가고 재시도 헤더는 뗀다."""
    harness = make_harness(RetryPolicy(max_attempts=2, mode=RetryMode.DELAYED))
    harness.add("first", fail)

    harness.handle(
        make_message(
            topic="SampleEvent.retry",
            partition=0,
            offset=7,
            headers={
                "x-custom": "kept",
                DeadLetterHeaderKey.ORIGINAL_TOPIC.value: "SampleEvent",
                DeadLetterHeaderKey.ORIGINAL_PARTITION.value: "3",
                DeadLetterHeaderKey.ORIGINAL_OFFSET.value: "42",
                DeadLetterHeaderKey.ORIGINAL_TIMESTAMP.value: "1690000000000",
                **DeliveryState(attempt=2, pending=frozenset({"first"})).to_headers(),
                DeliveryHeader.NOT_BEFORE.value: "999.0",
            },
        )
    )

    [record] = harness.published()
    assert record.topic == "SampleEvent.dlt"
    assert record.headers["x-custom"] == "kept"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == "SampleEvent"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_PARTITION] == "3"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "42"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_TIMESTAMP] == "1690000000000"
    assert not any(key in record.headers for key in DeliveryHeader)
    assert DeadLetter.from_headers(record.headers).attempts == 2
    assert harness.committed() == [("SampleEvent.retry", 0, 8)]


def test_worker_retry_record_failing_again_expect_republished_with_next_attempt(
    make_harness: HarnessFactory,
) -> None:
    """retry 레코드가 또 실패하고 시도가 남으면 다음 시도 번호로 retry 토픽에 다시 발행한다."""
    harness = make_harness(
        RetryPolicy(max_attempts=4, initial_interval=1.0, mode=RetryMode.DELAYED)
    )
    harness.add("first", fail)

    harness.handle(
        make_message(
            topic="SampleEvent.retry",
            partition=0,
            offset=7,
            headers={
                DeadLetterHeaderKey.ORIGINAL_OFFSET.value: "42",
                **DeliveryState(attempt=2, pending=frozenset({"first"})).to_headers(),
                DeliveryHeader.NOT_BEFORE.value: "999.0",
            },
        )
    )

    [record] = harness.published()
    assert record.topic == "SampleEvent.retry"
    assert DeliveryState.from_headers(record.headers).attempt == 3
    assert record.headers[DeliveryHeader.NOT_BEFORE] == "1002.0"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "42"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_PARTITION] == "0"


def test_worker_retry_record_with_malformed_state_expect_dead_letter_without_handler(
    make_harness: HarnessFactory,
) -> None:
    """재시도 상태를 읽을 수 없는 retry 레코드는 핸들러 호출 없이 dead-letter로 간다."""
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    handler = MagicMock()
    harness.add("first", handler)

    harness.handle(
        make_message(
            topic="SampleEvent.retry",
            partition=0,
            offset=7,
            headers={DeliveryHeader.ATTEMPT.value: "not-a-number"},
        )
    )

    handler.assert_not_called()
    [record] = harness.published()
    assert record.topic == "SampleEvent.dlt"
    assert record.headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == (
        "InvalidDeliveryHeaderError"
    )
    assert harness.committed() == [("SampleEvent.retry", 0, 8)]


def test_worker_deferred_retry_record_expect_remembered_state_used_on_redelivery(
    make_harness: HarnessFactory, clock: Clock
) -> None:
    """retry 레코드가 지연을 요청하면 기억한 상태로 같은 시도를 다시 전달한다."""
    harness = make_harness(RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED))
    attempts: list[int] = []

    def gated(event: SampleEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise EventDeferredError(retry_after=2.0)

    harness.add("gated", gated)
    retry = make_message(
        topic="SampleEvent.retry",
        partition=0,
        offset=7,
        headers=DeliveryState(attempt=2, pending=frozenset({"gated"})).to_headers(),
    )

    harness.handle(retry)
    clock.advance(2.0)
    harness.resume_due()
    harness.handle(retry)

    assert attempts == [2, 2]
    assert harness.committed() == [("SampleEvent.retry", 0, 8)]


def test_worker_dead_letter_refused_expect_position_rewound_without_commit(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """dead-letter 레코드가 브로커에 닿지 않으면 커밋하지 않고 되감아 다시 받는다."""
    harness = make_harness()
    harness.add("first", fail)
    harness.refuse_publish()

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Delivery to SampleEvent.dlt failed" in caplog.text
    assert harness.committed() == []
    assert harness.sought() == [ORIGIN]
    assert harness.paused() == []


def test_worker_rewind_rejected_expect_logged_and_loop_survives(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """되감기가 거절돼도 예외를 밖으로 내보내지 않고 기록한다."""
    harness = make_harness()
    harness.add("first", fail)
    harness.refuse_publish()
    harness.consumer.seek.side_effect = KafkaException(KafkaError(KafkaError._STATE))

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Cannot rewind SampleEvent [3] to offset 42" in caplog.text


def test_worker_commit_failure_expect_logged_and_loop_survives(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """커밋 호출이 실패해도 poll 루프를 죽이지 않고 기록한다."""
    harness = make_harness()
    harness.add("first", MagicMock())
    harness.consumer.commit.side_effect = KafkaException(
        KafkaError(KafkaError.REBALANCE_IN_PROGRESS)
    )

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Offset commit failed for SampleEvent" in caplog.text


def test_worker_commit_rejected_for_partition_expect_error_logged(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """브로커가 파티션 단위로 커밋을 거절하면 그 사실을 기록한다."""
    harness = make_harness()
    harness.add("first", MagicMock())
    rejected = MagicMock(
        topic="SampleEvent",
        partition=3,
        error=KafkaError(KafkaError.REBALANCE_IN_PROGRESS),
    )
    accepted = MagicMock(topic="SampleEvent", partition=4, error=None)
    harness.consumer.commit.return_value = [accepted, rejected]

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Offset commit rejected for SampleEvent [3]" in caplog.text
    assert "SampleEvent [4]" not in caplog.text


def test_worker_auth_boundary_handler_expect_record_headers_passed(
    make_harness: HarnessFactory,
) -> None:
    """auth 경계 엔드포인트만 Kafka 헤더를 키워드 인자로 받는다."""
    harness = make_harness()
    boundary = MagicMock()
    plain = MagicMock()
    harness.add("boundary", boundary, auth_boundary=True)
    harness.add("plain", plain)

    harness.handle(make_message(headers={"x-custom": "kept"}))

    assert boundary.call_args.kwargs == {
        KAFKA_AUTH_HEADERS_PARAMETER: {"x-custom": "kept"}
    }
    assert plain.call_args.kwargs == {}


def test_worker_auth_denied_expect_committed_without_dead_letter(
    make_harness: HarnessFactory,
) -> None:
    """인가 거부는 다시 보내도 바뀌지 않으므로 dead-letter 없이 커밋한다."""
    harness = make_harness(RetryPolicy(max_attempts=3))
    handler = MagicMock(side_effect=AuthRequirementDeniedError())
    harness.add("first", handler)

    harness.handle(make_message())

    assert handler.call_count == 1
    assert harness.published() == []
    assert harness.committed() == [COMMITTED]


def test_worker_auth_provider_unavailable_expect_propagated_and_uncommitted(
    make_harness: HarnessFactory,
) -> None:
    """인증 기반이 내려가면 메시지에 대한 판정이 아니므로 커밋 없이 예외를 전파한다."""
    harness = make_harness()
    harness.add(
        "first", MagicMock(side_effect=AuthVerificationProviderUnavailableError())
    )
    harness.set_propagator(W3CTracePropagator())

    with pytest.raises(AuthVerificationProviderUnavailableError):
        harness.handle(make_message())

    assert harness.committed() == []
    assert harness.published() == []
    assert TraceContext.get() is None


def test_worker_traceparent_header_expect_child_context_during_handler_then_cleared(
    make_harness: HarnessFactory,
) -> None:
    """traceparent 헤더가 있으면 핸들러는 그 자식 컨텍스트 안에서 실행되고 끝나면 지워진다."""
    harness = make_harness()
    harness.set_propagator(W3CTracePropagator())
    captured: list[TraceContext | None] = []
    harness.add("first", lambda event: captured.append(TraceContext.get()))

    harness.handle(make_message(headers={"traceparent": SAMPLE_TRACEPARENT}))

    [context] = captured
    assert context is not None
    assert context.trace_id == SAMPLE_TRACE_ID
    assert context.parent_span_id == SAMPLE_SPAN_ID
    assert TraceContext.get() is None


def test_worker_no_traceparent_header_expect_new_root_context(
    make_harness: HarnessFactory,
) -> None:
    """trace 헤더가 없으면 새 루트 컨텍스트에서 핸들러를 실행한다."""
    harness = make_harness()
    harness.set_propagator(W3CTracePropagator())
    captured: list[TraceContext | None] = []
    harness.add("first", lambda event: captured.append(TraceContext.get()))

    harness.handle(make_message())

    [context] = captured
    assert context is not None
    assert context.parent_span_id is None


def test_worker_without_propagator_expect_no_trace_context(
    make_harness: HarnessFactory,
) -> None:
    """propagator가 없으면 trace 컨텍스트를 만들지 않는다."""
    harness = make_harness()
    captured: list[TraceContext | None] = []
    harness.add("first", lambda event: captured.append(TraceContext.get()))

    harness.handle(make_message(headers={"traceparent": SAMPLE_TRACEPARENT}))

    assert captured == [None]


def test_worker_run_expect_due_partitions_resumed_and_polled_messages_delivered(
    make_harness: HarnessFactory,
) -> None:
    """poll 루프는 받은 메시지를 전달하고, 빈 poll과 정지 요청 뒤의 메시지는 넘긴다."""
    harness = make_harness()
    calls: list[str] = []
    harness.add("first", lambda event: calls.append(event.data))

    harness.run([make_message(), None, make_message(offset=43)])

    assert calls == ["hello"]
    assert harness.committed() == [COMMITTED]


def test_worker_run_auth_provider_unavailable_expect_loop_ends_with_error(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """인증 기반 장애는 이 구독자의 poll 루프를 끝내고 어느 그룹인지 기록한다."""
    harness = make_harness(subscriber="billing")
    harness.add(
        "first", MagicMock(side_effect=AuthVerificationProviderUnavailableError())
    )

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(AuthVerificationProviderUnavailableError),
    ):
        harness.run([make_message(), None])

    assert "Subscriber group test-group.billing stopped consuming" in caplog.text
    assert harness.committed() == []


def test_worker_open_expect_own_group_and_subscription_with_rebalance_callbacks(
    make_harness: HarnessFactory,
) -> None:
    """worker는 자기 group으로 consumer를 열고 이벤트·retry 토픽을 구독한다."""
    harness = make_harness(
        RetryPolicy(max_attempts=2, mode=RetryMode.DELAYED), subscriber="billing"
    )
    harness.add("first", MagicMock())
    harness.add("other", MagicMock(), AnotherEvent)

    consumer_cls, producer_cls = harness.open()

    assert consumer_cls.call_args.args[0]["group.id"] == "test-group.billing"
    assert consumer_cls.call_args.args[0]["enable.auto.commit"] is False
    producer_cls.assert_called_once()
    subscribe = consumer_cls.return_value.subscribe.call_args.kwargs
    assert subscribe["topics"] == [
        "SampleEvent",
        "AnotherEvent",
        "SampleEvent.billing.retry",
        "AnotherEvent.billing.retry",
    ]
    assert {"on_assign", "on_revoke", "on_lost"} <= set(subscribe)


def test_worker_close_expect_clients_released(make_harness: HarnessFactory) -> None:
    """worker를 닫으면 producer를 비우고 consumer group을 떠난다."""
    harness = make_harness()
    harness.add("first", MagicMock())

    harness.close()

    harness.consumer.close.assert_called_once()
    if isinstance(harness, SyncWorkerHarness):
        harness.producer.flush.assert_called_once_with(
            harness.config.dead_letter_delivery_timeout
        )
    if isinstance(harness, AsyncWorkerHarness):
        harness.producer.stop.assert_awaited_once()


def test_worker_redrive_expect_only_failed_handlers_run_and_offsets_committed(
    make_harness: HarnessFactory,
) -> None:
    """redrive는 dead letter마다 실패로 기록된 핸들러만 실행하고 성공하면 오프셋을 커밋한다."""
    harness = make_harness()
    calls: list[str] = []
    harness.add("first", lambda event: calls.append("first"))
    harness.add("second", lambda event: calls.append("second"))

    run = harness.redrive([dead_letter(0), None, dead_letter(1)], high=2)

    assert run.result == RedriveResult(succeeded=2, failed=0)
    assert calls == ["first", "first"]
    assert run.consumer_config["group.id"] == "test-group.redrive"
    [assigned] = run.consumer.assign.call_args.args[0]
    assert (assigned.topic, assigned.partition, assigned.offset) == (
        "SampleEvent.dlt",
        0,
        0,
    )
    committed = [
        call.kwargs["offsets"][0].offset for call in run.consumer.commit.call_args_list
    ]
    assert committed == [1, 2]
    assert run.published == []
    run.consumer.close.assert_called_once()
    assert harness.committed() == []


def test_worker_redrive_legacy_dead_letter_expect_every_handler_run(
    make_harness: HarnessFactory,
) -> None:
    """핸들러 메타데이터가 없는 예전 dead letter는 모든 핸들러를 실행한다."""
    harness = make_harness()
    calls: list[str] = []
    harness.add("first", lambda event: calls.append("first"))
    harness.add("second", lambda event: calls.append("second"))
    legacy = {DeadLetterHeaderKey.ORIGINAL_TOPIC.value: "SampleEvent"}

    run = harness.redrive([dead_letter(0, legacy)], high=1)

    assert run.result == RedriveResult(succeeded=1, failed=0)
    assert calls == ["first", "second"]


def test_worker_redrive_handler_no_longer_registered_expect_dead_letter_kept_as_failed(
    make_harness: HarnessFactory,
) -> None:
    """실패로 기록된 핸들러가 더 이상 없으면 dead letter를 성공으로 소비하지 않고 남긴다."""
    harness = make_harness()
    remaining = MagicMock()
    harness.add("first", remaining)

    run = harness.redrive(
        [dead_letter(0, dead_letter_headers(pending=("renamed-away",)))], high=1
    )

    assert run.result == RedriveResult(succeeded=0, failed=1)
    remaining.assert_not_called()
    [record] = run.published
    assert record.headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == (
        "EventHandlerNotRegisteredError"
    )
    assert DeadLetter.from_headers(record.headers).pending == frozenset(
        {"renamed-away"}
    )


def test_worker_redrive_failing_again_expect_republished_to_dead_letter_then_committed(
    make_harness: HarnessFactory,
) -> None:
    """다시 실패한 dead letter는 새 메타데이터로 DLT 끝에 다시 저장한 뒤 커밋한다."""
    harness = make_harness()
    harness.add("first", fail)
    harness.add("second", MagicMock())

    run = harness.redrive([dead_letter(4)], committed=4, high=5)

    assert run.result == RedriveResult(succeeded=0, failed=1)
    [record] = run.published
    assert record.topic == "SampleEvent.dlt"
    assert record.value == SAMPLE_PAYLOAD
    assert record.headers["x-custom"] == "kept"
    assert record.headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "42"
    assert record.headers[DeadLetterHeaderKey.EXCEPTION_MESSAGE] == (
        "cannot process hello"
    )
    dead = DeadLetter.from_headers(record.headers)
    assert dead.attempts == 2
    assert dead.pending == frozenset({"first"})
    assert run.consumer.assign.call_args.args[0][0].offset == 4
    assert run.consumer.commit.call_args.kwargs["offsets"][0].offset == 5


def test_worker_redrive_republish_refused_expect_dead_letter_left_uncommitted(
    make_harness: HarnessFactory,
) -> None:
    """다시 저장하지 못한 dead letter는 커밋하지 않고 redrive를 멈춘다."""
    harness = make_harness()
    handler = MagicMock(side_effect=RuntimeError("still failing"))
    harness.add("first", handler)

    run = harness.redrive([dead_letter(0), dead_letter(1)], high=2, refuse_publish=True)

    assert run.result == RedriveResult(succeeded=0, failed=1)
    assert handler.call_count == 1
    run.consumer.commit.assert_not_called()
    run.consumer.close.assert_called_once()


def test_worker_redrive_limit_expect_only_that_many_dead_letters_taken(
    make_harness: HarnessFactory,
) -> None:
    """limit은 이번 호출에서 가져갈 dead letter 수를 제한한다."""
    harness = make_harness()
    handler = MagicMock()
    harness.add("first", handler)

    run = harness.redrive([dead_letter(0), dead_letter(1)], limit=1, high=2)

    assert run.result == RedriveResult(succeeded=1, failed=0)
    assert handler.call_count == 1


def test_worker_redrive_record_past_start_end_expect_not_delivered(
    make_harness: HarnessFactory,
) -> None:
    """호출이 시작된 뒤 쌓인 dead letter는 이번 호출에서 전달하지 않는다."""
    harness = make_harness()
    handler = MagicMock()
    harness.add("first", handler)

    run = harness.redrive([dead_letter(3), dead_letter(4)], committed=3, high=3, low=0)
    late = harness.redrive([dead_letter(3)], committed=2, high=3)

    assert run.result == RedriveResult(succeeded=0, failed=0)
    run.consumer.poll.assert_not_called()
    assert late.result == RedriveResult(succeeded=0, failed=0)
    handler.assert_not_called()
    late.consumer.pause.assert_called_once()
    late.consumer.commit.assert_not_called()


def test_worker_redrive_unknown_dead_letter_topic_expect_nothing_done(
    make_harness: HarnessFactory,
) -> None:
    """dead-letter 토픽이 아직 없으면 아무것도 읽지 않는다."""
    harness = make_harness()
    harness.add("first", MagicMock())

    run = harness.redrive([], topic_known=False)

    assert run.result == RedriveResult(succeeded=0, failed=0)
    run.consumer.assign.assert_not_called()


def test_worker_redrive_unusable_polls_expect_skipped(
    make_harness: HarnessFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """오류 이벤트·좌표 없는 메시지·이미 끝난 파티션의 레코드는 건너뛴다."""
    harness = make_harness()
    handler = MagicMock()
    harness.add("first", handler)
    broker_error = dead_letter(0)
    broker_error.error.return_value = KafkaError(KafkaError._PARTITION_EOF)
    malformed = dead_letter(0)
    malformed.partition.return_value = None
    other_partition = make_message(topic="SampleEvent.dlt", partition=5, offset=0)

    with caplog.at_level(logging.WARNING):
        run = harness.redrive(
            [broker_error, malformed, other_partition, dead_letter(0)], high=1
        )

    assert run.result == RedriveResult(succeeded=1, failed=0)
    assert handler.call_count == 1
    assert "Redrive consumer error on SampleEvent.dlt" in caplog.text
    assert "no topic, partition or offset" in caplog.text


def test_worker_redrive_broker_silent_expect_stopped_after_timeout(
    make_harness: HarnessFactory, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    """브로커가 dead letter를 내주지 않으면 redrive_timeout 뒤에 멈춘다."""
    harness = make_harness()
    harness.add("first", MagicMock())
    clock.step = 4.0

    with caplog.at_level(logging.WARNING):
        run = harness.redrive([], high=2)

    assert run.result == RedriveResult(succeeded=0, failed=0)
    assert "Redrive of SampleEvent.dlt stopped" in caplog.text
    run.consumer.close.assert_called_once()


def test_worker_redrive_auth_provider_unavailable_expect_propagated_and_uncommitted(
    make_harness: HarnessFactory,
) -> None:
    """redrive 중 인증 기반이 내려가면 dead letter를 커밋하지 않고 예외를 전파한다."""
    harness = make_harness()
    harness.add(
        "first", MagicMock(side_effect=AuthVerificationProviderUnavailableError())
    )

    with pytest.raises(AuthVerificationProviderUnavailableError):
        harness.redrive([dead_letter(0)], high=1)

    harness.redrive_consumer.commit.assert_not_called()
    harness.redrive_consumer.close.assert_called_once()


def test_sync_worker_local_queue_full_expect_dead_letter_not_committed(
    config: KafkaConnectionConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """로컬 큐가 가득 차 produce가 거절돼도 poll 스레드를 죽이지 않고 커밋하지 않는다."""
    harness = SyncWorkerHarness(config, None)
    harness.add("first", fail)
    harness.producer.produce.side_effect = BufferError("queue full")

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Delivery to SampleEvent.dlt failed: queue full" in caplog.text
    harness.producer.flush.assert_not_called()
    assert harness.committed() == []


def test_sync_worker_flush_timeout_expect_dead_letter_not_committed(
    config: KafkaConnectionConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """flush가 제한 시간 안에 끝나지 않으면 전달되지 않은 것으로 보고 커밋하지 않는다."""
    harness = SyncWorkerHarness(config, None)
    harness.add("first", fail)
    harness.producer.flush.return_value = 1

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Record for SampleEvent.dlt still unsent after 10.0s" in caplog.text
    harness.producer.flush.assert_called_once_with(10.0)
    assert harness.committed() == []


def test_sync_worker_broker_rejects_record_expect_dead_letter_not_committed(
    config: KafkaConnectionConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """flush는 끝났지만 delivery callback이 거절을 알리면 커밋하지 않는다."""
    harness = SyncWorkerHarness(config, None)
    harness.add("first", fail)
    harness.producer.produce.side_effect = lambda **kwargs: kwargs["callback"](
        KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED), MagicMock()
    )

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Delivery to SampleEvent.dlt failed" in caplog.text
    assert harness.committed() == []
    assert harness.sought() == [ORIGIN]


def test_async_worker_unconfirmed_delivery_expect_dead_letter_not_committed(
    config: KafkaConnectionConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """확인을 제한 시간 안에 받지 못하면 중복 가능성을 알리고 커밋하지 않는다."""
    harness = AsyncWorkerHarness(config, None)
    harness.config.dead_letter_delivery_timeout = 0.01
    harness.add("first", fail)

    async def never_confirmed(**kwargs: object) -> None:
        await asyncio.Event().wait()

    harness.producer.send_and_wait.side_effect = never_confirmed

    with caplog.at_level(logging.ERROR):
        harness.handle(make_message())

    assert "Delivery to SampleEvent.dlt unconfirmed after 0.01s" in caplog.text
    assert "it may still be delivered" in caplog.text
    assert harness.committed() == []
