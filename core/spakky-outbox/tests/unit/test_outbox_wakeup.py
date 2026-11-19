"""Tests for OutboxRelayWakeup."""

import pytest

from spakky.outbox.relay.wakeup import OutboxRelayWakeup


class RelayWakeFailedError(Exception):
    """A relay that cannot be woken, e.g. because its event loop is closed."""


def test_wakeup_notify_expect_every_subscriber_woken() -> None:
    """notify는 구독한 relay를 모두 깨운다."""
    wakeup = OutboxRelayWakeup()
    woken: list[str] = []
    wakeup.subscribe(lambda: woken.append("first"))
    wakeup.subscribe(lambda: woken.append("second"))

    wakeup.notify()

    assert woken == ["first", "second"]


def test_wakeup_subscribe_twice_expect_woken_once() -> None:
    """같은 relay를 두 번 구독해도 한 번만 깨운다."""
    wakeup = OutboxRelayWakeup()
    woken: list[str] = []

    def waker() -> None:
        woken.append("woken")

    wakeup.subscribe(waker)
    wakeup.subscribe(waker)
    wakeup.notify()

    assert woken == ["woken"]


def test_wakeup_unsubscribe_expect_no_longer_woken() -> None:
    """구독을 해제한 relay는 깨우지 않는다."""
    wakeup = OutboxRelayWakeup()
    woken: list[str] = []

    def waker() -> None:
        woken.append("woken")

    wakeup.subscribe(waker)
    wakeup.unsubscribe(waker)
    wakeup.notify()

    assert woken == []


def test_wakeup_failing_subscriber_expect_logged_and_others_woken(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """깨우지 못한 relay는 로그로 남기고 나머지 relay는 깨운다."""
    wakeup = OutboxRelayWakeup()
    woken: list[str] = []

    def failing() -> None:
        raise RelayWakeFailedError()

    wakeup.subscribe(failing)
    wakeup.subscribe(lambda: woken.append("woken"))

    with caplog.at_level("ERROR"):
        wakeup.notify()

    assert woken == ["woken"]
    assert "Failed to wake outbox relay" in caplog.text
