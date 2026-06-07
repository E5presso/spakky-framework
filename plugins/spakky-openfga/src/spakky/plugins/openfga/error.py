"""Error classes for the spakky-openfga plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractOpenFgaError(AbstractSpakkyFrameworkError, ABC):
    """Base class for OpenFGA provider errors."""

    ...


class OpenFgaProviderUnavailableError(AbstractOpenFgaError):
    """Raised when the OpenFGA check provider cannot be reached or used."""

    message = "OpenFGA provider is unavailable"


class OpenFgaReferenceMappingError(AbstractOpenFgaError):
    """Raised when canonical auth refs cannot be mapped to OpenFGA refs."""

    message = "OpenFGA reference mapping failed"
