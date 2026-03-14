"""Tests for main.py initialize function."""

from unittest.mock import MagicMock, call

from spakky.plugins.celery.aspects.task_dispatch import (
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.common.config import CeleryConfig
from spakky.plugins.celery.main import initialize
from spakky.plugins.celery.post_processor import CeleryPostProcessor


def test_initialize_registers_all_components() -> None:
    """initialize가 모든 컴포넌트를 app에 등록하는지 검증한다."""
    app = MagicMock()

    initialize(app)

    expected_calls = [
        call(CeleryConfig),
        call(CeleryPostProcessor),
        call(CeleryTaskDispatchAspect),
        call(AsyncCeleryTaskDispatchAspect),
    ]
    app.add.assert_has_calls(expected_calls, any_order=False)
    assert app.add.call_count == 4
