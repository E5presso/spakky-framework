"""Tests for AG-UI plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.main import initialize


def test_initialize_registers_agui_config_pod() -> None:
    """initialize()가 AgUiConfig Pod을 컨테이너에 등록한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(AgUiConfig)
    app.start()
    assert isinstance(app.container.get(AgUiConfig), AgUiConfig)
