"""Unit tests for main.py initialize function."""

from unittest.mock import MagicMock, call

from spakky.tracing.main import initialize
from spakky.tracing.w3c_propagator import W3CTracePropagator


def test_initialize_expect_w3c_propagator_registered() -> None:
    """initialize()가 W3CTracePropagator를 DI 컨테이너에 등록하는지 검증한다."""
    app = MagicMock()

    initialize(app)

    app.add.assert_has_calls([call(W3CTracePropagator)], any_order=False)
    assert app.add.call_count == 1
