"""Tests for plugin initialization."""

from spakky.agent import IAgentModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.main import initialize
from spakky.plugins.vllm.model import VllmAgentModel


def test_initialize_registers_vllm_model_adapter_binding() -> None:
    """initialize()가 config/client/model과 IAgentModel binding을 등록한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(VllmConfig)
    assert app.container.contains(HttpxVllmChatClient)
    assert app.container.contains(VllmAgentModel)
    app.start()
    assert isinstance(app.container.get(IAgentModel), VllmAgentModel)
