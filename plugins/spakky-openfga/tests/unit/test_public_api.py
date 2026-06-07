import pytest

import spakky.plugins.openfga as openfga_api
from spakky.core.application.plugin import Plugin
from spakky.plugins.openfga import (
    IOpenFgaCheckClient,
    OpenFgaAuthProvider,
    OpenFgaCheckRequest,
    OpenFgaCheckResult,
    OpenFgaConfig,
    OpenFgaProviderUnavailableError,
    OpenFgaReferenceMappingError,
    OpenFgaSdkCheckClient,
)


def test_public_api_exports_openfga_provider_contracts() -> None:
    assert openfga_api.PLUGIN_NAME == Plugin(name="spakky-openfga")
    assert IOpenFgaCheckClient is openfga_api.IOpenFgaCheckClient
    assert OpenFgaAuthProvider is openfga_api.OpenFgaAuthProvider
    assert OpenFgaCheckRequest is openfga_api.OpenFgaCheckRequest
    assert OpenFgaCheckResult is openfga_api.OpenFgaCheckResult
    assert OpenFgaConfig is openfga_api.OpenFgaConfig
    assert (
        OpenFgaProviderUnavailableError is openfga_api.OpenFgaProviderUnavailableError
    )
    assert OpenFgaReferenceMappingError is openfga_api.OpenFgaReferenceMappingError
    assert OpenFgaSdkCheckClient is openfga_api.OpenFgaSdkCheckClient


def test_config_reads_openfga_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPAKKY_OPENFGA_API_URL", "http://openfga.example")
    monkeypatch.setenv("SPAKKY_OPENFGA_STORE_ID", "store-env")
    monkeypatch.setenv("SPAKKY_OPENFGA_AUTHORIZATION_MODEL_ID", "model-env")

    config = OpenFgaConfig()

    assert config.api_url == "http://openfga.example"
    assert config.store_id == "store-env"
    assert config.authorization_model_id == "model-env"
