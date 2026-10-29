"""Generic consumer deferral contract."""

import pytest
from spakky.event import EventDeferredError, InvalidEventDeferralError


def test_deferred_error_expect_positive_default_and_explicit_delay() -> None:
    """기본/명시 delay는 소비자가 native poll을 유지하며 재시도할 계약이다."""
    assert EventDeferredError().retry_after == 1.0
    assert EventDeferredError(12.5).retry_after == 12.5


@pytest.mark.parametrize("delay", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_deferral_expect_rejected(delay: float) -> None:
    """무한 대기 또는 busy loop를 만드는 delay는 설정 시 거부한다."""
    with pytest.raises(InvalidEventDeferralError):
        EventDeferredError(delay)
