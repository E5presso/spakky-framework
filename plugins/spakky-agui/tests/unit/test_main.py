"""Tests for AG-UI plugin initialization."""

from unittest.mock import MagicMock

from spakky.agent import AgentRunnerFactory, IAgentRunnerFactory
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.main import initialize
from spakky.plugins.agui.post_processors.mount_fastapi import (
    MountAgUiFastAPIPostProcessor,
)
from spakky.plugins.agui.server.registry import AgUiAgentRegistry


def test_initialize_registers_agui_plugin_pods() -> None:
    """initialize()가 AG-UI config, registry, post-processor를 등록한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(AgUiConfig)
    assert app.container.contains(AgUiAgentRegistry)
    assert app.container.contains(MountAgUiFastAPIPostProcessor)
    app.start()
    assert isinstance(app.container.get(AgUiConfig), AgUiConfig)
    assert isinstance(app.container.get(AgUiAgentRegistry), AgUiAgentRegistry)


def test_initialize_reuses_existing_runner_factory_binding() -> None:
    """IAgentRunnerFactory가 이미 있으면 기본 AgentRunnerFactory를 추가하지 않는다."""
    app = MagicMock(spec=SpakkyApplication)
    app.container.contains.return_value = True

    initialize(app)

    added = [called.args[0] for called in app.add.call_args_list]
    assert AgentRunnerFactory not in added
    assert AgUiConfig in added
    app.container.contains.assert_called_once_with(IAgentRunnerFactory)
