"""OpenFGA check client boundary and SDK adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import override

from openfga_sdk.client import ClientCheckRequest, ClientConfiguration
from openfga_sdk.exceptions import ApiException, FgaValidationException
from openfga_sdk.sync import OpenFgaClient
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.error import OpenFgaProviderUnavailableError


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenFgaCheckRequest:
    """Provider-local tuple check request mapped from Spakky auth refs."""

    user: str
    """OpenFGA user string."""

    relation: str
    """OpenFGA relation string."""

    object: str
    """OpenFGA object string."""


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenFgaCheckResult:
    """Provider-local check result."""

    allowed: bool
    """Whether OpenFGA allowed the tuple check."""


class IOpenFgaCheckClient(ABC):
    """Boundary used by the auth provider to execute OpenFGA checks."""

    @abstractmethod
    def check(self, request: OpenFgaCheckRequest) -> OpenFgaCheckResult:
        """Execute an OpenFGA check request."""
        ...


@Pod()
class OpenFgaSdkCheckClient(IOpenFgaCheckClient):
    """Synchronous OpenFGA SDK-backed check client."""

    _config: OpenFgaConfig

    def __init__(self, config: OpenFgaConfig = OpenFgaConfig()) -> None:
        self._config = config

    @override
    def check(self, request: OpenFgaCheckRequest) -> OpenFgaCheckResult:
        """Execute an OpenFGA check request with the official SDK."""
        try:
            with OpenFgaClient(self._client_configuration()) as client:
                response = client.check(
                    ClientCheckRequest(
                        user=request.user,
                        relation=request.relation,
                        object=request.object,
                    )
                )
        except (ApiException, FgaValidationException) as e:
            raise OpenFgaProviderUnavailableError from e
        return OpenFgaCheckResult(allowed=response.allowed is True)

    def _client_configuration(self) -> ClientConfiguration:
        return ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
            authorization_model_id=self._config.authorization_model_id,
        )
