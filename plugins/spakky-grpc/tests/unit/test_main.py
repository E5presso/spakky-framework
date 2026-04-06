"""Unit tests for gRPC plugin main.py initialize function."""

from unittest.mock import MagicMock, call

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.grpc.main import initialize
from spakky.plugins.grpc.post_processors.add_interceptors import (
    AddInterceptorsPostProcessor,
)
from spakky.plugins.grpc.post_processors.bind_server import (
    BindServerPostProcessor,
)
from spakky.plugins.grpc.post_processors.register_services import (
    RegisterServicesPostProcessor,
)


def test_initialize_registers_all_post_processors() -> None:
    """initialize() should register all three PostProcessors."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_any_call(RegisterServicesPostProcessor)
    app.add.assert_any_call(AddInterceptorsPostProcessor)
    app.add.assert_any_call(BindServerPostProcessor)
    assert app.add.call_count == 3


def test_initialize_registration_order() -> None:
    """PostProcessors should be registered in the expected order."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    expected_calls = [
        call(RegisterServicesPostProcessor),
        call(AddInterceptorsPostProcessor),
        call(BindServerPostProcessor),
    ]
    app.add.assert_has_calls(expected_calls, any_order=False)
