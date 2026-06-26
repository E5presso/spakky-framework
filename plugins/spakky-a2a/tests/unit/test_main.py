"""Unit tests for the A2A plugin initialize function."""

from unittest.mock import MagicMock, call

from spakky.agent import AgentRunnerFactory, IAgentDelegate, IAgentRunnerFactory
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.a2a.config import A2AConfig
from spakky.plugins.a2a.delegation import A2AAgentDelegate
from spakky.plugins.a2a.main import initialize
from spakky.plugins.a2a.post_processors.mount_asgi import MountA2AASGIPostProcessor
from spakky.plugins.a2a.post_processors.register_agent_servers import (
    RegisterA2AAgentServersPostProcessor,
)
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry


def test_initialize_registers_plugin_pods() -> None:
    """initialize() registers config, registry, server spec, and post-processor."""
    app = MagicMock(spec=SpakkyApplication)
    app.container.contains.return_value = False

    initialize(app)

    app.add.assert_has_calls(
        [
            call(AgentRunnerFactory),
            call(A2AConfig),
            call(A2AAgentDelegate),
            call(A2AAgentRegistry),
            call(A2AAgentServerSpec),
            call(RegisterA2AAgentServersPostProcessor),
            call(MountA2AASGIPostProcessor),
        ],
        any_order=False,
    )
    app.container.contains.assert_called_once_with(IAgentRunnerFactory)
    app.container.bind_to_type.assert_called_once_with(IAgentDelegate, A2AAgentDelegate)
    assert app.add.call_count == 7


def test_initialize_reuses_existing_runner_factory_binding() -> None:
    """IAgentRunnerFactory가 이미 있으면 기본 AgentRunnerFactory를 추가하지 않는다."""
    app = MagicMock(spec=SpakkyApplication)
    app.container.contains.return_value = True

    initialize(app)

    added = [called.args[0] for called in app.add.call_args_list]
    assert AgentRunnerFactory not in added
    assert A2AConfig in added
    app.container.contains.assert_called_once_with(IAgentRunnerFactory)
