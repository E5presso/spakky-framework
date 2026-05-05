"""Tests for spakky-vllm public API exports."""

import spakky.plugins.vllm as vllm_api
from spakky.plugins.vllm import (
    HttpxVllmChatClient,
    IVllmChatClient,
    PLUGIN_NAME,
    VllmAgentModel,
    VllmConfig,
    VllmModelRefusalError,
    VllmResponseError,
    VllmStreamingDisabledError,
    VllmStreamingNotImplementedError,
    VllmTimeoutError,
    VllmTransportError,
)


def test_public_api_exports_vllm_surface() -> None:
    """public API가 plugin id, config, client, model, error surface를 노출한다."""
    assert PLUGIN_NAME.name == "spakky-vllm"
    assert VllmConfig is vllm_api.VllmConfig
    assert IVllmChatClient is vllm_api.IVllmChatClient
    assert HttpxVllmChatClient is vllm_api.HttpxVllmChatClient
    assert VllmAgentModel is vllm_api.VllmAgentModel
    assert VllmModelRefusalError is vllm_api.VllmModelRefusalError
    assert VllmResponseError is vllm_api.VllmResponseError
    assert VllmStreamingDisabledError is vllm_api.VllmStreamingDisabledError
    assert VllmStreamingNotImplementedError is vllm_api.VllmStreamingNotImplementedError
    assert VllmTimeoutError is vllm_api.VllmTimeoutError
    assert VllmTransportError is vllm_api.VllmTransportError
