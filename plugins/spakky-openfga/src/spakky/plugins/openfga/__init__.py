"""OpenFGA relationship authorization provider plugin for Spakky Auth."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.openfga.client import (
    IOpenFgaCheckClient,
    OpenFgaCheckRequest,
    OpenFgaCheckResult,
    OpenFgaSdkCheckClient,
)
from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.error import (
    AbstractOpenFgaError,
    OpenFgaProviderUnavailableError,
    OpenFgaReferenceMappingError,
)
from spakky.plugins.openfga.provider import (
    OpenFgaAuthProvider,
    openfga_auth_provider_contribution,
)

PLUGIN_NAME = Plugin(name="spakky-openfga")
"""Plugin identifier for the OpenFGA auth provider package."""

__all__ = [
    "AbstractOpenFgaError",
    "IOpenFgaCheckClient",
    "OpenFgaAuthProvider",
    "OpenFgaCheckRequest",
    "OpenFgaCheckResult",
    "OpenFgaConfig",
    "OpenFgaProviderUnavailableError",
    "OpenFgaReferenceMappingError",
    "OpenFgaSdkCheckClient",
    "PLUGIN_NAME",
    "openfga_auth_provider_contribution",
]
