"""Unit tests for the mapping between delivery state and Kafka records."""

import logging
from unittest.mock import MagicMock

import pytest
from confluent_kafka import KafkaError
from spakky.event.delivery import (
    DeadLetter,
    DeliveryDeadLettered,
    DeliveryDeferred,
    DeliveryHeader,
    DeliveryRetry,
    DeliveryState,
    HandlerFailure,
)
from spakky.event.error import InvalidDeliveryHeaderError, InvalidMessageError

from spakky.plugins.kafka.common.constants import DeadLetterHeaderKey
from spakky.plugins.kafka.event.records import (
    ConsumedRecord,
    KafkaDeadLetters,
    KafkaDeliveryHeaders,
    KafkaDeliveryReport,
)
from tests.unit.harness import make_message

FAILURE = HandlerFailure(
    handler="charge",
    exception_type="RuntimeError",
    exception_message="gateway down",
    retryable=True,
)


def test_consumed_record_from_message_expect_coordinates_and_decoded_headers() -> None:
    """polled 메시지는 좌표와 문자열 헤더를 가진 레코드로 읽힌다."""
    record = ConsumedRecord.from_message(make_message(headers={"x-custom": "kept"}))

    assert record.coordinates == ("SampleEvent", 3, 42)
    assert record.partition_key == ("SampleEvent", 3)
    assert record.headers == {"x-custom": "kept"}
    assert record.timestamp == 1700000000000
    assert record.position.offset == 42
    assert record.next_position.offset == 43


def test_consumed_record_from_message_without_topic_expect_invalid_message_error() -> (
    None
):
    """토픽을 알 수 없는 메시지는 레코드로 읽을 수 없다."""
    message = make_message()
    message.topic.return_value = None

    with pytest.raises(InvalidMessageError):
        ConsumedRecord.from_message(message)


def test_headers_decode_with_list_of_bytes_expect_strings() -> None:
    """bytes 값의 튜플 리스트 헤더는 문자열 dict로 디코딩된다."""
    assert KafkaDeliveryHeaders.decode(
        [("traceparent", b"00-abc-def-01"), ("custom", b"value")]
    ) == {"traceparent": "00-abc-def-01", "custom": "value"}


def test_headers_decode_with_mixed_dict_values_expect_none_skipped() -> None:
    """dict 헤더에서 str은 유지하고 bytes는 디코딩하며 None은 건너뛴다."""
    assert KafkaDeliveryHeaders.decode(
        {"text": "plain", "binary": b"raw", "absent": None}
    ) == {"text": "plain", "binary": "raw"}


def test_headers_decode_with_none_expect_empty() -> None:
    """헤더가 없으면 빈 dict를 돌려준다."""
    assert KafkaDeliveryHeaders.decode(None) == {}


def test_headers_encode_expect_byte_valued_pairs() -> None:
    """문자열 헤더는 비동기 producer가 받는 bytes 쌍으로 인코딩된다."""
    assert KafkaDeliveryHeaders.encode({"a": "1"}) == [("a", b"1")]


def test_headers_not_before_without_header_expect_due_at_once() -> None:
    """구독자가 예약하지 않은 레코드는 바로 실행할 수 있다."""
    assert KafkaDeliveryHeaders.not_before({}) == 0.0


def test_headers_not_before_with_malformed_value_expect_invalid_header_error() -> None:
    """숫자가 아닌 실행 가능 시각은 잘못된 헤더로 거절한다."""
    with pytest.raises(InvalidDeliveryHeaderError):
        KafkaDeliveryHeaders.not_before({DeliveryHeader.NOT_BEFORE.value: "soon"})


def test_headers_previous_attempts_expect_recorded_count_or_zero_for_legacy() -> None:
    """dead letter에 기록된 시도 횟수를 읽고, 메타데이터가 없으면 0으로 본다."""
    recorded = DeadLetter(
        event_name="SampleEvent",
        subscriber="billing",
        failures=(FAILURE,),
        attempts=3,
        failed_at="2026-01-01T00:00:00+00:00",
    ).to_headers()

    assert KafkaDeliveryHeaders.previous_attempts(recorded) == 3
    assert KafkaDeliveryHeaders.previous_attempts({}) == 0
    assert KafkaDeliveryHeaders.redrive_pending(recorded) == frozenset({"charge"})
    assert KafkaDeliveryHeaders.redrive_pending({}) is None


def test_headers_dead_letter_without_failures_expect_no_exception_headers() -> None:
    """실패 목록이 빈 dead letter는 예외 헤더 없이 나머지 메타데이터만 싣는다."""
    record = ConsumedRecord.from_message(make_message())
    dead_letter = DeadLetter(
        event_name="SampleEvent",
        subscriber=None,
        failures=(),
        attempts=1,
        failed_at="2026-01-01T00:00:00+00:00",
    )

    headers = KafkaDeliveryHeaders.dead_letter(
        record, "SampleEvent", False, "test-group", dead_letter
    )

    assert DeadLetterHeaderKey.EXCEPTION_TYPE not in headers
    assert headers[DeadLetterHeaderKey.CONSUMER_GROUP] == "test-group"


def test_dead_letters_after_redrive_with_retry_outcome_expect_its_failures_kept() -> (
    None
):
    """redrive 시도가 재시도 판정으로 끝나면 그 실패를 dead letter의 새 상태로 남긴다."""
    outcome = DeliveryRetry(
        state=DeliveryState(attempt=2, pending=frozenset({"charge"})),
        delay=1.0,
        failures=(FAILURE,),
    )

    dead_letter = KafkaDeadLetters.after_redrive("SampleEvent", "billing", outcome, 2)

    assert dead_letter.failures == (FAILURE,)
    assert dead_letter.attempts == 3
    assert dead_letter.subscriber == "billing"


def test_dead_letters_after_redrive_with_dead_lettered_outcome_expect_failures_kept() -> (
    None
):
    """redrive 시도가 dead-letter 판정으로 끝나면 그 실패 목록과 누적 시도 횟수를 남긴다."""
    outcome = DeliveryDeadLettered(
        dead_letter=DeadLetter(
            event_name="SampleEvent",
            subscriber="billing",
            failures=(FAILURE,),
            attempts=1,
            failed_at="2026-01-01T00:00:00+00:00",
        )
    )

    dead_letter = KafkaDeadLetters.after_redrive("SampleEvent", "billing", outcome, 0)

    assert dead_letter.failures == (FAILURE,)
    assert dead_letter.attempts == 1


def test_dead_letters_after_redrive_with_deferred_outcome_expect_pending_handlers_recorded() -> (
    None
):
    """redrive 중 지연을 요청한 핸들러는 다음 redrive가 실행할 실패로 기록된다."""
    outcome = DeliveryDeferred(
        state=DeliveryState(pending=frozenset({"charge", "audit"})), retry_after=5.0
    )

    dead_letter = KafkaDeadLetters.after_redrive("SampleEvent", None, outcome, 1)

    assert [failure.handler for failure in dead_letter.failures] == ["audit", "charge"]
    assert {failure.exception_type for failure in dead_letter.failures} == {
        "EventDeferredError"
    }
    assert dead_letter.pending == frozenset({"charge", "audit"})


def test_delivery_report_with_broker_error_expect_undelivered_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """브로커가 거절한 레코드는 전달되지 않은 것으로 남고 오류가 기록된다."""
    report = KafkaDeliveryReport("SampleEvent.dlt")

    with caplog.at_level(logging.ERROR):
        report.on_delivery(
            KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED), MagicMock()
        )

    assert report.delivered is False
    assert "Delivery to SampleEvent.dlt failed" in caplog.text


def test_delivery_report_without_error_expect_delivered() -> None:
    """브로커가 받아들인 레코드는 전달된 것으로 기록된다."""
    report = KafkaDeliveryReport("SampleEvent.dlt")

    report.on_delivery(None, MagicMock())

    assert report.delivered is True
