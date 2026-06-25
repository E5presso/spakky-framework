"""Unit tests for the A2A plugin initialize function."""

from unittest.mock import MagicMock, call

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.a2a.config import A2AConfig
from spakky.plugins.a2a.main import initialize
from spakky.plugins.a2a.post_processors.register_agent_servers import (
    RegisterA2AAgentServersPostProcessor,
)
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry


def test_initialize_registers_plugin_pods() -> None:
    """initialize() registers config, registry, server spec, and post-processor."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_has_calls(
        [
            call(A2AConfig),
            call(A2AAgentRegistry),
            call(A2AAgentServerSpec),
            call(RegisterA2AAgentServersPostProcessor),
        ],
        any_order=False,
    )
    assert app.add.call_count == 4
