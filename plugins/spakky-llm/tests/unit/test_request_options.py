"""Tests for per-request route overrides carried by LlmRequestOptions."""

from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from math import inf
from typing import cast, override

import pytest
from pydantic import SecretStr, ValidationError
from spakky.agent import (
    JsonValue,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
    ModelStreamEventKind,
)

from spakky.plugins.llm.cache import (
    ILLMCacheScopeResolver,
    ILLMResponseCache,
    LlmCachedResponse,
    LlmCacheKeyBuilder,
    LlmCacheLookup,
    LlmCacheMode,
    LlmCachePolicy,
    LlmCacheScope,
)
from spakky.plugins.llm.config import (
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    LlmReasoningEffort,
    LlmScalar,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.error import (
    LlmFailureClass,
    LlmModelSelectionError,
    LlmRequestOptionsError,
    LlmTransportError,
    LlmUnsupportedFeatureError,
)
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    LlmRequestOptions,
    done_event,
    routing_metadata,
)


class _RecordingProvider(ILLMProvider):
    """Record every resolved target and fail the refs it is told to fail."""

    def __init__(
        self,
        apis: frozenset[LlmProviderApi],
        failing_refs: frozenset[str] = frozenset(),
    ) -> None:
        self.__apis = apis
        self.__failing_refs = failing_refs
        self.targets: list[LlmModelTarget] = []

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        return self.__apis

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        self.targets.append(target)
        if target.model_ref in self.__failing_refs:
            raise LlmTransportError
        return ModelResponse(content="ok")

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        self.targets.append(target)
        return self._stream(target)

    async def _stream(self, target: LlmModelTarget) -> AsyncIterator[ModelStreamEvent]:
        yield done_event(target, "stop", None)


def _config() -> LlmConfig:
    return LlmConfig(
        default_model="core",
        profiles={
            "local": LlmProfile(
                provider="vllm",
                api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                base_url="http://localhost:8000/v1",
                openai_dialect=OpenAICompatibleDialect.VLLM,
            ),
            "gateway": LlmProfile(
                provider="openai",
                api=LlmProviderApi.OPENAI_RESPONSES,
                api_key=SecretStr("secret"),
            ),
            "standard": LlmProfile(
                provider="openai",
                api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                api_key=SecretStr("secret"),
            ),
        },
        models={
            "core": LlmModelRoute(
                profile="local",
                model="local-model",
                chat_template_kwargs={"enable_thinking": False, "budget": 64},
                fallbacks=("backup",),
                fallback_on=frozenset({LlmFailureClass.TRANSPORT}),
            ),
            "backup": LlmModelRoute(
                profile="local",
                model="backup-model",
                chat_template_kwargs={"enable_thinking": False},
            ),
            "gpt": LlmModelRoute(
                profile="gateway",
                model="gpt-default",
                reasoning_effort=LlmReasoningEffort.LOW,
            ),
            "plain": LlmModelRoute(profile="standard", model="plain-model"),
        },
    )


def _providers(
    failing_refs: frozenset[str] = frozenset(),
) -> tuple[_RecordingProvider, _RecordingProvider]:
    return (
        _RecordingProvider(
            frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS}),
            failing_refs,
        ),
        _RecordingProvider(frozenset({LlmProviderApi.OPENAI_RESPONSES})),
    )


def _request(model_ref: str, options: LlmRequestOptions | None) -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        model_selection=ModelSelection(model_ref=model_ref),
        extensions=() if options is None else (options,),
    )


async def test_request_without_options_expect_catalog_route_unchanged() -> None:
    """Without LlmRequestOptions the adapter receives the catalog route as is."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))

    await model.complete(_request("core", None))

    assert chat.targets[0].route == _config().models["core"]


async def test_request_options_expect_overridden_route_for_selected_model() -> None:
    """Model and template kwargs override the selected route after revalidation."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))
    options = LlmRequestOptions(
        model="  tuned-model  ",
        chat_template_kwargs={"enable_thinking": "true"},
        extra_body={"add_generation_prompt": False},
    )

    response = await model.complete(_request("core", options))

    target = chat.targets[0]
    assert target.model == "tuned-model"
    assert target.route.chat_template_kwargs == {
        "enable_thinking": True,
        "budget": 64,
    }
    assert target.route.extra_body == {"add_generation_prompt": False}
    assert target.route.fallbacks == ("backup",)
    assert routing_metadata(target)["model"] == "tuned-model"
    assert response.metadata["attempted_model_ref"] == "core"


async def test_request_options_expect_fallback_routes_not_overridden() -> None:
    """Fallback refs name other models, so they keep their own catalog values."""
    chat, responses = _providers(failing_refs=frozenset({"core"}))
    model = LlmAgentModel(_config(), (chat, responses))
    options = LlmRequestOptions(
        model="tuned-model",
        chat_template_kwargs={"enable_thinking": True},
    )

    await model.complete(_request("core", options))

    assert [target.model for target in chat.targets] == [
        "tuned-model",
        "backup-model",
    ]
    assert chat.targets[1].route == _config().models["backup"]


async def test_request_options_expect_stream_uses_overridden_route() -> None:
    """Streaming resolves the same overridden route as completion."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))

    events = [
        event
        async for event in model.stream(
            _request("core", LlmRequestOptions(model="stream-model"))
        )
    ]

    assert events[-1].kind is ModelStreamEventKind.DONE
    assert chat.targets[0].model == "stream-model"


async def test_request_options_reasoning_effort_expect_responses_route_override() -> (
    None
):
    """Reasoning effort overrides a Responses route; None keeps the route's value."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))

    await model.complete(
        _request("gpt", LlmRequestOptions(reasoning_effort=LlmReasoningEffort.HIGH))
    )
    await model.complete(_request("gpt", LlmRequestOptions(model="gpt-other")))

    assert responses.targets[0].route.reasoning_effort is LlmReasoningEffort.HIGH
    assert responses.targets[1].route.reasoning_effort is LlmReasoningEffort.LOW
    assert responses.targets[1].model == "gpt-other"


@pytest.mark.parametrize(
    ("model_ref", "options"),
    [
        ("gpt", LlmRequestOptions(chat_template_kwargs={"enable_thinking": True})),
        ("plain", LlmRequestOptions(extra_body={"top_k": 20})),
        ("core", LlmRequestOptions(reasoning_effort=LlmReasoningEffort.HIGH)),
    ],
)
async def test_request_options_unsupported_by_profile_expect_unsupported_error(
    model_ref: str,
    options: LlmRequestOptions,
) -> None:
    """Template kwargs and extra body need vLLM; reasoning effort needs Responses."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))

    with pytest.raises(LlmUnsupportedFeatureError):
        await model.complete(_request(model_ref, options))
    with pytest.raises(LlmUnsupportedFeatureError):
        model.validate_request(_request(model_ref, options))

    assert chat.targets == []
    assert responses.targets == []


async def test_request_options_unsupported_in_stream_expect_error_event() -> None:
    """Streaming reports an unsupported override as a terminal error event."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))

    events = [
        event
        async for event in model.stream(
            _request("plain", LlmRequestOptions(extra_body={"top_k": 20}))
        )
    ]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert events[0].error is not None
    assert events[0].error.code == "llm_feature_unsupported"
    assert events[0].metadata["model_ref"] == "plain"
    assert chat.targets == []


@pytest.mark.parametrize(
    "options",
    [
        LlmRequestOptions(model="   "),
        LlmRequestOptions(extra_body={"chat_template_kwargs": {"x": True}}),
        LlmRequestOptions(extra_body={"structured_outputs": {"json": {}}}),
    ],
)
async def test_invalid_request_options_expect_request_options_error(
    options: LlmRequestOptions,
) -> None:
    """A blank model or a framework-owned extra body key fails route revalidation."""
    chat, responses = _providers()
    model = LlmAgentModel(_config(), (chat, responses))

    with pytest.raises(LlmRequestOptionsError) as raised:
        await model.complete(_request("core", options))

    assert isinstance(raised.value, LlmModelSelectionError)
    assert chat.targets == []


@pytest.mark.parametrize(
    ("model", "chat_template_kwargs", "reasoning_effort", "extra_body"),
    [
        (7, {}, None, {}),
        (None, {"x": None}, None, {}),
        (None, {"x": inf}, None, {}),
        (None, {1: True}, None, {}),
        (None, ["x"], None, {}),
        (None, {}, "high", {}),
        (None, {}, None, {"x": object()}),
        (None, {}, None, ["x"]),
    ],
)
def test_request_options_invalid_values_expect_request_options_error(
    model: object,
    chat_template_kwargs: object,
    reasoning_effort: object,
    extra_body: object,
) -> None:
    """Options reject values that are not template scalars or JSON at construction."""
    # Casts deliberately smuggle untyped caller values past the static signature.
    with pytest.raises(LlmRequestOptionsError):
        LlmRequestOptions(
            model=cast(str | None, model),
            chat_template_kwargs=cast(Mapping[str, LlmScalar], chat_template_kwargs),
            reasoning_effort=cast(LlmReasoningEffort | None, reasoning_effort),
            extra_body=cast(Mapping[str, JsonValue], extra_body),
        )


def test_request_options_expect_snapshot_that_survives_deepcopy() -> None:
    """Options copy caller mappings so later mutation and deepcopy cannot leak."""
    kwargs: dict[str, LlmScalar] = {"enable_thinking": True}
    body: dict[str, JsonValue] = {"stop": ["a", {"b": 1.5}]}
    options = LlmRequestOptions(chat_template_kwargs=kwargs, extra_body=body)
    kwargs["enable_thinking"] = False
    body["stop"] = []

    copied = deepcopy(_request("core", options)).extension(LlmRequestOptions)

    assert options.chat_template_kwargs == {"enable_thinking": True}
    assert options.extra_body == {"stop": ("a", {"b": 1.5})}
    assert copied == options


def _cache_target(route: LlmModelRoute) -> LlmModelTarget:
    return LlmModelTarget(
        model_ref="core",
        profile_name="local",
        profile=_config().profiles["local"],
        route=route,
    )


def test_cache_key_expect_extra_body_and_reasoning_effort_partition() -> None:
    """Overridden extra body and reasoning effort change the exact cache key."""
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    scope = LlmCacheScope("tenant-a", "redaction-v1")
    request = _request("core", None)
    route = LlmModelRoute(profile="local", model="local-model")
    base = LlmCacheKeyBuilder.build(policy, scope, _cache_target(route), request)
    body = LlmCacheKeyBuilder.build(
        policy,
        scope,
        _cache_target(route.model_copy(update={"extra_body": {"top_k": 20}})),
        request,
    )
    effort = LlmCacheKeyBuilder.build(
        policy,
        scope,
        _cache_target(
            route.model_copy(update={"reasoning_effort": LlmReasoningEffort.HIGH})
        ),
        request,
        reasoning_effort_overridden=True,
    )

    assert len({base.key.digest, body.key.digest, effort.key.digest}) == 3


def test_cache_key_catalog_reasoning_effort_expect_digest_unchanged() -> None:
    """A catalog reasoning effort without a request override keeps the old key."""
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    scope = LlmCacheScope("tenant-a", "redaction-v1")
    request = _request("core", None)
    route = LlmModelRoute(profile="local", model="local-model")
    base = LlmCacheKeyBuilder.build(policy, scope, _cache_target(route), request)
    catalog_effort = LlmCacheKeyBuilder.build(
        policy,
        scope,
        _cache_target(
            route.model_copy(update={"reasoning_effort": LlmReasoningEffort.HIGH})
        ),
        request,
    )

    assert catalog_effort.key.digest == base.key.digest


def test_route_extra_body_reserved_key_expect_validation_error() -> None:
    """Operators cannot set framework-owned request keys through extra_body."""
    with pytest.raises(ValidationError) as raised:
        LlmModelRoute(
            profile="local",
            model="local-model",
            extra_body={"structured_outputs": {}},
        )

    assert raised.value.errors()[0]["type"] == "llm_model_route_extra_body_reserved"


def test_route_extra_body_outside_vllm_expect_validation_error() -> None:
    """A catalog route with extra_body requires a vLLM connection profile."""
    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model="plain",
            profiles={"standard": _config().profiles["standard"]},
            models={
                "plain": LlmModelRoute(
                    profile="standard",
                    model="plain-model",
                    extra_body={"top_k": 20},
                )
            },
        )

    assert raised.value.errors()[0]["type"] == "llm_model_route_extra_body"


def test_chat_completions_credential_provider_expect_valid_profile() -> None:
    """Chat-completions profiles may resolve their token through a credential provider."""
    profile = LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        credential_provider="caller-token",
    )

    assert profile.credential_provider == "caller-token"
    assert profile.api_key is None


class _LookupRecordingCache(ILLMResponseCache):
    """Exact cache that never hits and records every lookup key."""

    def __init__(self) -> None:
        self.lookups: list[LlmCacheLookup] = []

    @property
    @override
    def mode(self) -> LlmCacheMode:
        return LlmCacheMode.EXACT

    @override
    async def lookup(self, query: LlmCacheLookup) -> LlmCachedResponse | None:
        self.lookups.append(query)
        return None

    @override
    async def store(
        self,
        query: LlmCacheLookup,
        response: LlmCachedResponse,
        *,
        ttl_seconds: float,
    ) -> None:
        _ = (query, response, ttl_seconds)


class _FixedScopeResolver(ILLMCacheScopeResolver):
    @override
    def resolve(self, request: ModelRequest) -> LlmCacheScope:
        _ = request
        return LlmCacheScope("tenant-a", "redaction-v1")


async def test_cached_route_reasoning_effort_override_expect_only_override_partitions() -> (
    None
):
    """Without options the catalog effort stays out of the key; an override enters it."""
    config = _config()
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    config.models["gpt"] = config.models["gpt"].model_copy(update={"cache": policy})
    cache = _LookupRecordingCache()
    chat, responses = _providers()
    model = LlmAgentModel(
        config,
        (chat, responses),
        response_caches=(cache,),
        cache_scope_resolver=_FixedScopeResolver(),
    )

    await model.complete(_request("gpt", None))
    await model.complete(
        _request("gpt", LlmRequestOptions(reasoning_effort=LlmReasoningEffort.HIGH))
    )

    catalog_target = responses.targets[0]
    without_effort = LlmCacheKeyBuilder.build(
        policy,
        LlmCacheScope("tenant-a", "redaction-v1"),
        LlmModelTarget(
            model_ref=catalog_target.model_ref,
            profile_name=catalog_target.profile_name,
            profile=catalog_target.profile,
            route=catalog_target.route.model_copy(update={"reasoning_effort": None}),
        ),
        _request("gpt", None),
    )
    assert cache.lookups[0].key.digest == without_effort.key.digest
    assert cache.lookups[1].key.digest != cache.lookups[0].key.digest
