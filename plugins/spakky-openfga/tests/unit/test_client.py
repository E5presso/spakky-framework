from dataclasses import dataclass
from types import TracebackType

import pytest
from openfga_sdk.exceptions import ApiException, FgaValidationException

from spakky.plugins.openfga import client as client_module
from spakky.plugins.openfga.client import OpenFgaCheckRequest, OpenFgaSdkCheckClient
from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.error import OpenFgaProviderUnavailableError


@dataclass(frozen=True, slots=True)
class FakeSdkResponse:
    allowed: bool


class FakeOpenFgaClient:
    instances: list["FakeOpenFgaClient"] = []
    response: FakeSdkResponse = FakeSdkResponse(allowed=True)
    unavailable: bool = False

    def __init__(self, configuration: object) -> None:
        self.configuration = configuration
        self.requests: list[object] = []
        self.instances.append(self)

    def __enter__(self) -> "FakeOpenFgaClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def check(self, request: object) -> FakeSdkResponse:
        if self.unavailable:
            raise ApiException("unavailable")
        self.requests.append(request)
        return self.response


class FakeValidationOpenFgaClient(FakeOpenFgaClient):
    def check(self, request: object) -> FakeSdkResponse:
        raise FgaValidationException("invalid authorization model id")


def test_sdk_client_maps_check_request_to_openfga_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeOpenFgaClient.instances = []
    FakeOpenFgaClient.response = FakeSdkResponse(allowed=True)
    FakeOpenFgaClient.unavailable = False
    monkeypatch.setattr(client_module, "OpenFgaClient", FakeOpenFgaClient)
    client = OpenFgaSdkCheckClient(
        OpenFgaConfig().model_copy(
            update={
                "api_url": "http://openfga.test",
                "store_id": "store-1",
                "authorization_model_id": "model-1",
            }
        )
    )

    result = client.check(
        OpenFgaCheckRequest(
            user="user:alice",
            relation="viewer",
            object="document:doc-1",
        )
    )

    assert result.allowed is True
    assert len(FakeOpenFgaClient.instances) == 1
    assert len(FakeOpenFgaClient.instances[0].requests) == 1


def test_sdk_client_maps_api_exception_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeOpenFgaClient.instances = []
    FakeOpenFgaClient.unavailable = True
    monkeypatch.setattr(client_module, "OpenFgaClient", FakeOpenFgaClient)
    client = OpenFgaSdkCheckClient(OpenFgaConfig())

    with pytest.raises(OpenFgaProviderUnavailableError):
        client.check(
            OpenFgaCheckRequest(
                user="user:alice",
                relation="viewer",
                object="document:doc-1",
            )
        )


def test_sdk_client_maps_validation_exception_to_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "OpenFgaClient", FakeValidationOpenFgaClient)
    client = OpenFgaSdkCheckClient(OpenFgaConfig())

    with pytest.raises(OpenFgaProviderUnavailableError):
        client.check(
            OpenFgaCheckRequest(
                user="user:alice",
                relation="viewer",
                object="document:doc-1",
            )
        )
