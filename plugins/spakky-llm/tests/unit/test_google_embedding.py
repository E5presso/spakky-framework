"""Tests for the Google text-embedding adapter."""

from collections.abc import Sequence
from typing import cast
from unittest.mock import patch

import httpx
import pytest
from google.auth.exceptions import (
    RefreshError,
    TransportError as GoogleAuthTransportError,
)
from google.genai import errors, types
from pydantic import SecretStr
from spakky.agent import EmbeddingPurpose, ModelCapability

from spakky.plugins.llm.config import (
    GoogleCredentialStrategy,
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
)
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmConfigurationError,
    LlmResponseError,
    LlmTimeoutError,
    LlmTransportError,
)
from spakky.plugins.llm.provider import LlmModelTarget
from spakky.plugins.llm.providers.google import (
    GoogleGenerateContentProvider,
    GoogleTextEmbedding,
)


class _EmbeddingModels:
    def __init__(
        self,
        response: types.EmbedContentResponse,
        *,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.model: str | None = None
        self.contents: list[str] | None = None
        self.config: types.EmbedContentConfig | None = None

    async def embed_content(
        self,
        *,
        model: str,
        contents: Sequence[str],
        config: types.EmbedContentConfig,
    ) -> types.EmbedContentResponse:
        self.model = model
        self.contents = list(contents)
        self.config = config
        if self._error is not None:
            raise self._error
        return self._response


class _EmbeddingAsyncClient:
    def __init__(self, models: _EmbeddingModels) -> None:
        self.models = models
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> "_EmbeddingAsyncClient":
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.exited = True


class _EmbeddingClient:
    def __init__(self, models: _EmbeddingModels) -> None:
        self.aio = _EmbeddingAsyncClient(models)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _response(
    *values: list[float] | None,
    truncated: bool | None = None,
) -> types.EmbedContentResponse:
    return types.EmbedContentResponse(
        embeddings=[
            types.ContentEmbedding(
                values=value,
                statistics=(
                    types.ContentEmbeddingStatistics(truncated=truncated)
                    if truncated is not None
                    else None
                ),
            )
            for value in values
        ]
    )


def _config(
    *,
    api: LlmProviderApi = LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
) -> LlmConfig:
    profile = (
        LlmProfile(
            provider="google",
            api=api,
            api_key=SecretStr("google-key"),
            google_credential_strategy=GoogleCredentialStrategy.API_KEY,
        )
        if api == LlmProviderApi.GOOGLE_GEMINI_DEVELOPER
        else LlmProfile(
            provider="google",
            api=api,
            google_credential_strategy=GoogleCredentialStrategy.ADC,
            google_project="project",
            google_location="us-central1",
        )
        if api == LlmProviderApi.GOOGLE_VERTEX
        else LlmProfile(
            provider="foreign",
            api=api,
            api_key=SecretStr("key"),
        )
    )
    return LlmConfig(
        default_model="embedding/default",
        profiles={"embedding": profile},
        models={
            "embedding/default": LlmModelRoute(
                profile="embedding",
                model="gemini-embedding-001",
                capability=ModelCapability(),
            )
        },
    )


@pytest.mark.parametrize(
    ("purpose", "task_type"),
    [
        (EmbeddingPurpose.QUERY, "RETRIEVAL_QUERY"),
        (EmbeddingPurpose.DOCUMENT, "RETRIEVAL_DOCUMENT"),
    ],
)
async def test_google_embedding_maps_batch_task_and_dimension(
    purpose: EmbeddingPurpose,
    task_type: str,
) -> None:
    models = _EmbeddingModels(
        _response([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], truncated=False)
    )
    client = _EmbeddingClient(models)
    embedding = GoogleTextEmbedding.from_config(
        _config(),
        "embedding/default",
        output_dimensionality=3,
    )

    with patch.object(
        GoogleGenerateContentProvider,
        "_client",
        return_value=client,
    ) as create_client:
        vectors = await embedding.embed(("first", "second"), purpose)

    assert [vector.values for vector in vectors] == [
        (1.0, 2.0, 3.0),
        (4.0, 5.0, 6.0),
    ]
    assert all(vector.dimension == 3 for vector in vectors)
    assert all(vector.normalized is False for vector in vectors)
    assert models.model == "gemini-embedding-001"
    assert models.contents == ["first", "second"]
    assert models.config is not None
    assert models.config.task_type == task_type
    assert models.config.output_dimensionality == 3
    assert client.aio.entered and client.aio.exited and client.closed
    assert create_client.call_args.kwargs["timeout_seconds"] == 30.0


def test_google_embedding_catalog_snapshot_and_configuration_guards() -> None:
    config = _config(api=LlmProviderApi.GOOGLE_VERTEX)
    embedding = GoogleTextEmbedding.from_config(config, "embedding/default")
    config.models["embedding/default"] = LlmModelRoute(
        profile="embedding",
        model="changed",
    )

    assert embedding._target.model == "gemini-embedding-001"
    assert embedding._target.profile.api == LlmProviderApi.GOOGLE_VERTEX
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding.from_config(config, " ")
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding.from_config(config, cast(str, 1))
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding.from_config(config, "missing")
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding.from_config(
            _config(api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS),
            "embedding/default",
        )
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding(embedding._target, output_dimensionality=0)
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding(embedding._target, output_dimensionality=cast(int, True))
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding(embedding._target, output_dimensionality=cast(int, 1.5))

    missing_profile = _config()
    missing_profile.profiles.clear()
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding.from_config(missing_profile, "embedding/default")


@pytest.mark.parametrize(
    "target",
    [
        LlmModelTarget(
            model_ref=cast(str, 1),
            profile_name="embedding",
            profile=_config().profiles["embedding"],
            route=_config().models["embedding/default"],
        ),
        LlmModelTarget(
            model_ref=" ",
            profile_name="embedding",
            profile=_config().profiles["embedding"],
            route=_config().models["embedding/default"],
        ),
        LlmModelTarget(
            model_ref="embedding/default",
            profile_name=cast(str, 1),
            profile=_config().profiles["embedding"],
            route=_config().models["embedding/default"],
        ),
        LlmModelTarget(
            model_ref="embedding/default",
            profile_name=" ",
            profile=_config().profiles["embedding"],
            route=_config().models["embedding/default"],
        ),
        LlmModelTarget(
            model_ref="embedding/default",
            profile_name="other",
            profile=_config().profiles["embedding"],
            route=_config().models["embedding/default"],
        ),
        LlmModelTarget(
            model_ref="embedding/default",
            profile_name="embedding",
            profile=_config().profiles["embedding"],
            route=LlmModelRoute.model_construct(
                profile="embedding",
                model=cast(str, 1),
            ),
        ),
        LlmModelTarget(
            model_ref="embedding/default",
            profile_name="embedding",
            profile=_config().profiles["embedding"],
            route=LlmModelRoute.model_construct(
                profile="embedding",
                model=" ",
            ),
        ),
    ],
)
def test_google_embedding_rejects_malformed_direct_targets(
    target: LlmModelTarget,
) -> None:
    with pytest.raises(LlmConfigurationError):
        GoogleTextEmbedding(target)


@pytest.mark.parametrize(
    ("texts", "purpose"),
    [
        ((), EmbeddingPurpose.QUERY),
        (cast(Sequence[str], "query"), EmbeddingPurpose.QUERY),
        ((" ",), EmbeddingPurpose.QUERY),
        ((cast(str, 1),), EmbeddingPurpose.QUERY),
        (("query",), cast(EmbeddingPurpose, "unknown")),
    ],
)
async def test_google_embedding_rejects_invalid_request_contracts(
    texts: Sequence[str],
    purpose: EmbeddingPurpose,
) -> None:
    embedding = GoogleTextEmbedding.from_config(_config(), "embedding/default")

    with pytest.raises(LlmConfigurationError):
        await embedding.embed(texts, purpose)


@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        (errors.ClientError(429, {"message": "rate limited"}), LlmTransportError),
        (TypeError("malformed"), LlmResponseError),
        (httpx.InvalidURL("invalid"), LlmConfigurationError),
        (httpx.ReadTimeout("slow"), LlmTimeoutError),
        (httpx.ConnectError("offline"), LlmTransportError),
        (GoogleAuthTransportError("offline"), LlmTransportError),
        (RefreshError("invalid credential"), LlmConfigurationError),
    ],
)
async def test_google_embedding_normalizes_sdk_failures(
    provider_error: Exception,
    expected_error: type[AbstractLlmError],
) -> None:
    models = _EmbeddingModels(_response([1.0]), error=provider_error)
    client = _EmbeddingClient(models)
    embedding = GoogleTextEmbedding.from_config(_config(), "embedding/default")

    with (
        patch.object(
            GoogleGenerateContentProvider,
            "_client",
            return_value=client,
        ),
        pytest.raises(expected_error),
    ):
        await embedding.embed(("query",), EmbeddingPurpose.QUERY)
    assert client.closed


@pytest.mark.parametrize(
    ("response", "output_dimensionality"),
    [
        (types.EmbedContentResponse(embeddings=None), None),
        (_response(), None),
        (_response(None), None),
        (
            types.EmbedContentResponse.model_construct(
                embeddings=[types.ContentEmbedding.model_construct(values=[True])]
            ),
            None,
        ),
        (
            types.EmbedContentResponse.model_construct(embeddings=[None]),
            None,
        ),
        (_response([]), None),
        (_response([float("nan")]), None),
        (_response([1.0], truncated=True), None),
        (_response([1.0, 2.0]), 3),
        (_response([1.0], [1.0, 2.0]), None),
    ],
)
async def test_google_embedding_rejects_malformed_success_payloads(
    response: types.EmbedContentResponse,
    output_dimensionality: int | None,
) -> None:
    models = _EmbeddingModels(response)
    client = _EmbeddingClient(models)
    embedding = GoogleTextEmbedding.from_config(
        _config(),
        "embedding/default",
        output_dimensionality=output_dimensionality,
    )
    texts = (
        ("one", "two")
        if response.embeddings and len(response.embeddings) == 2
        else ("one",)
    )

    with (
        patch.object(
            GoogleGenerateContentProvider,
            "_client",
            return_value=client,
        ),
        pytest.raises(LlmResponseError),
    ):
        await embedding.embed(texts, EmbeddingPurpose.QUERY)
    assert client.closed


async def test_google_embedding_rejects_non_response_sdk_value() -> None:
    models = _EmbeddingModels(cast(types.EmbedContentResponse, object()))
    client = _EmbeddingClient(models)
    embedding = GoogleTextEmbedding.from_config(_config(), "embedding/default")

    with (
        patch.object(
            GoogleGenerateContentProvider,
            "_client",
            return_value=client,
        ),
        pytest.raises(LlmResponseError),
    ):
        await embedding.embed(("one",), EmbeddingPurpose.QUERY)
