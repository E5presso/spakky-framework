"""Acceptance-style tests for resilient logical model orchestration."""

from asyncio import Event, create_task
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from typing import cast, override

import pytest
from pydantic import SecretStr
from spakky.agent import (
    JsonSchemaConstraint,
    JsonObject,
    JsonValue,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelModality,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolSpec,
    ModelUsage,
    StructuredOutputSpec,
    ToolCallingSpec,
)
from spakky.agent.content import ImagePart, model_content_text

from spakky.plugins.llm.cache import (
    ILLMCacheScopeResolver,
    ILLMResponseCache,
    LlmCachedResponse,
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
)
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmCacheConfigurationError,
    LlmCapabilityError,
    LlmConfigurationError,
    LlmFailureClass,
    LlmModelRefusalError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmTransportError,
)
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.media import ILLMMediaUriPolicy
from spakky.plugins.llm.provider import ILLMProvider, LlmModelTarget
from spakky.plugins.llm.resilience import (
    ILLMClock,
    LlmConcurrencyPolicy,
    LlmRateLimitPolicy,
    LlmResiliencePolicy,
    LlmRetryPolicy,
)


class RecordingClock(ILLMClock):
    """Deterministic retry clock for orchestration tests."""

    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []

    @override
    def now(self) -> float:
        return self.current

    @override
    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


class BlockingRetryClock(ILLMClock):
    """Expose retry sleep so another request can contend concurrently."""

    def __init__(self) -> None:
        self.started = Event()
        self.release_sleep = Event()

    @override
    def now(self) -> float:
        return 0.0

    @override
    async def sleep(self, seconds: float) -> None:
        _ = seconds
        self.started.set()
        await self.release_sleep.wait()


class SequencedProvider(ILLMProvider):
    """Provider whose per-route outcomes expose exact retry and fallback order."""

    def __init__(
        self,
        complete_outcomes: dict[str, list[ModelResponse | AbstractLlmError]],
        stream_outcomes: dict[
            str,
            list[tuple[ModelStreamEvent | AbstractLlmError, ...]],
        ]
        | None = None,
    ) -> None:
        self.complete_outcomes = complete_outcomes
        self.stream_outcomes = stream_outcomes or {}
        self.complete_calls: list[str] = []
        self.stream_calls: list[str] = []

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        return frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS})

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        _ = request
        self.complete_calls.append(target.model_ref)
        outcome = self.complete_outcomes[target.model_ref].pop(0)
        if isinstance(outcome, AbstractLlmError):
            raise outcome
        return outcome

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        _ = request
        self.stream_calls.append(target.model_ref)
        script = self.stream_outcomes[target.model_ref].pop(0)
        return self._stream(script)

    async def _stream(
        self,
        script: tuple[ModelStreamEvent | AbstractLlmError, ...],
    ) -> AsyncIterator[ModelStreamEvent]:
        for item in script:
            if isinstance(item, AbstractLlmError):
                raise item
            yield item


class RecordingResponseCache(ILLMResponseCache):
    """Explicit test cache implementing exactly one configured mode."""

    def __init__(self, mode: LlmCacheMode) -> None:
        self.__mode = mode
        self.entries: dict[str, LlmCachedResponse] = {}
        self.lookups: list[LlmCacheLookup] = []
        self.stores: list[LlmCacheLookup] = []

    @property
    @override
    def mode(self) -> LlmCacheMode:
        return self.__mode

    @override
    async def lookup(self, query: LlmCacheLookup) -> LlmCachedResponse | None:
        self.lookups.append(query)
        return self.entries.get(query.key.digest)

    @override
    async def store(
        self,
        query: LlmCacheLookup,
        response: LlmCachedResponse,
        *,
        ttl_seconds: float,
    ) -> None:
        assert ttl_seconds > 0
        self.stores.append(query)
        self.entries[query.key.digest] = response


class BlockingMissCache(RecordingResponseCache):
    """Cache miss exposing an async mutation window before provider dispatch."""

    def __init__(self) -> None:
        super().__init__(LlmCacheMode.EXACT)
        self.started = Event()
        self.release_lookup = Event()

    @override
    async def lookup(self, query: LlmCacheLookup) -> LlmCachedResponse | None:
        self.lookups.append(query)
        self.started.set()
        await self.release_lookup.wait()
        return self.entries.get(query.key.digest)


class RequestEchoProvider(SequencedProvider):
    """Provider whose response proves the exact request snapshot it observed."""

    def __init__(self) -> None:
        super().__init__({})

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        self.complete_calls.append(target.model_ref)
        marker = request.metadata.get("marker")
        return ModelResponse(
            content=f"seen:{model_content_text(request.messages[0].content)}:{marker}"
        )


class PrimaryRejectingMediaPolicy(ILLMMediaUriPolicy):
    """Target-aware media policy proving explicit fallback integration."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @override
    async def validate(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> None:
        _ = request
        self.calls.append(target.model_ref)
        if target.model_ref == "primary":
            raise LlmConfigurationError(details={"reason": "test_media_rejection"})


class RevokingMediaPolicy(ILLMMediaUriPolicy):
    """Stateful authority that revokes the same request after its first use."""

    def __init__(self) -> None:
        self.calls = 0

    @override
    async def validate(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> None:
        _ = (target, request)
        self.calls += 1
        if self.calls > 1:
            raise LlmConfigurationError(details={"reason": "media_revoked"})


class FixedCacheScopeResolver(ILLMCacheScopeResolver):
    """Trusted scope seam independent of request metadata."""

    @override
    def resolve(self, request: ModelRequest) -> LlmCacheScope:
        _ = request
        return LlmCacheScope("tenant-a", "redaction-v1")


class FailingCacheScopeResolver(ILLMCacheScopeResolver):
    @override
    def resolve(self, request: ModelRequest) -> LlmCacheScope:
        raise RuntimeError("scope failed")


class UntrustedResponseCache(RecordingResponseCache):
    def __init__(
        self,
        *,
        lookup_value: object = None,
        lookup_error: bool = False,
        typed_lookup_error: bool = False,
        store_error: bool = False,
        typed_store_error: bool = False,
    ) -> None:
        super().__init__(LlmCacheMode.EXACT)
        self.lookup_value = lookup_value
        self.lookup_error = lookup_error
        self.typed_lookup_error = typed_lookup_error
        self.store_error = store_error
        self.typed_store_error = typed_store_error

    @override
    async def lookup(self, query: LlmCacheLookup) -> LlmCachedResponse | None:
        if self.lookup_error:
            raise RuntimeError("lookup failed")
        if self.typed_lookup_error:
            raise LlmCacheConfigurationError
        return cast(LlmCachedResponse | None, self.lookup_value)

    @override
    async def store(
        self,
        query: LlmCacheLookup,
        response: LlmCachedResponse,
        *,
        ttl_seconds: float,
    ) -> None:
        if self.store_error:
            raise RuntimeError("store failed")
        if self.typed_store_error:
            raise LlmCacheConfigurationError
        await super().store(
            query,
            response,
            ttl_seconds=ttl_seconds,
        )


def _profile(
    *,
    retry: LlmRetryPolicy | None = None,
    resilience: LlmResiliencePolicy | None = None,
) -> LlmProfile:
    return LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        api_key=SecretStr("secret"),
        resilience=(
            resilience
            if resilience is not None
            else LlmResiliencePolicy(
                retry=retry if retry is not None else LlmRetryPolicy()
            )
        ),
    )


def _config(
    *,
    root_fallbacks: tuple[str, ...] = (),
    fallback_on: frozenset[LlmFailureClass] = frozenset(),
    retry: LlmRetryPolicy | None = None,
    primary_capability: ModelCapability | None = None,
    fallback_capability: ModelCapability | None = None,
    cache_mode: LlmCacheMode = LlmCacheMode.DISABLED,
    resilience: LlmResiliencePolicy | None = None,
) -> LlmConfig:
    return LlmConfig(
        default_model="primary",
        profiles={"profile": _profile(retry=retry, resilience=resilience)},
        models={
            "primary": LlmModelRoute(
                profile="profile",
                model="physical-primary",
                capability=primary_capability or ModelCapability(),
                fallbacks=root_fallbacks,
                fallback_on=fallback_on,
                cache=LlmCachePolicy(mode=cache_mode),
            ),
            "fallback": LlmModelRoute(
                profile="profile",
                model="physical-fallback",
                capability=fallback_capability or ModelCapability(),
            ),
        },
    )


def _request(*, with_tools: bool = False) -> ModelRequest:
    tools = None
    if with_tools:
        tools = ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    parameters=JsonSchemaConstraint(schema={"type": "object"}),
                ),
            )
        )
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        tool_calling=tools,
    )


def _attempts(metadata: JsonObject) -> tuple[Mapping[str, JsonValue], ...]:
    """Narrow public JSON metadata to its documented attempt evidence sequence."""
    value = metadata["attempts"]
    assert isinstance(value, Sequence)
    assert not isinstance(value, str)
    narrowed: list[Mapping[str, JsonValue]] = []
    for item in value:
        assert isinstance(item, Mapping)
        narrowed.append(item)
    return tuple(narrowed)


async def test_no_config_expect_exactly_one_attempt() -> None:
    """Disabled defaults perform one SDK call without retry or fallback."""
    provider = SequencedProvider({"primary": [ModelResponse(content="ok")]})
    model = LlmAgentModel(_config(), (provider,))

    response = await model.complete(_request())

    assert provider.complete_calls == ["primary"]
    assert response.metadata["attempt_ordinal"] == 1
    assert response.metadata["retry_count"] == 0
    assert response.metadata["fallback_used"] is False


async def test_complete_empty_internal_candidate_walk_expect_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An impossible empty internal traversal still returns a typed model failure."""

    def no_candidates(self: LlmAgentModel, model_ref: str) -> tuple[str, ...]:
        _ = (self, model_ref)
        return ()

    monkeypatch.setattr(LlmAgentModel, "_candidate_refs", no_candidates)
    model = LlmAgentModel(_config(), (SequencedProvider({}),))

    with pytest.raises(LlmCapabilityError):
        await model.complete(_request())


async def test_stream_empty_internal_candidate_walk_expect_typed_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An impossible empty stream traversal terminates with ERROR then DONE."""

    def no_candidates(self: LlmAgentModel, model_ref: str) -> tuple[str, ...]:
        _ = (self, model_ref)
        return ()

    monkeypatch.setattr(LlmAgentModel, "_candidate_refs", no_candidates)
    model = LlmAgentModel(_config(), (SequencedProvider({}, {}),))

    events = [event async for event in model.stream(_request())]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]


async def test_timeout_retry_then_success_expect_ordered_attempt_evidence() -> None:
    """Explicit timeout retry executes the same profile once more then succeeds."""
    retry = LlmRetryPolicy(
        max_attempts=2,
        failure_classes=frozenset({LlmFailureClass.TIMEOUT}),
    )
    provider = SequencedProvider(
        {"primary": [LlmTimeoutError(), ModelResponse(content="ok")]}
    )
    model = LlmAgentModel(_config(retry=retry), (provider,))

    response = await model.complete(_request())

    assert provider.complete_calls == ["primary", "primary"]
    assert response.metadata["retry_count"] == 1
    attempts = _attempts(response.metadata)
    assert attempts[0]["failure_class"] == "timeout"
    assert attempts[1]["state"] == "success"


async def test_retry_after_expect_typed_delay_used_before_success() -> None:
    """Rate-limit Retry-After controls the orchestration sleeper exactly."""
    clock = RecordingClock()
    retry = LlmRetryPolicy(
        max_attempts=2,
        backoff_seconds=1.0,
        failure_classes=frozenset({LlmFailureClass.RATE_LIMIT}),
    )
    provider = SequencedProvider(
        {
            "primary": [
                LlmRateLimitError(retry_after_seconds=4.5),
                ModelResponse(content="ok"),
            ]
        }
    )
    model = LlmAgentModel(_config(retry=retry), (provider,), clock=clock)

    response = await model.complete(_request())

    assert response.metadata["retry_count"] == 1
    assert clock.sleeps == [4.5]


async def test_retry_backoff_releases_concurrency_permit() -> None:
    """An independent request can run while the first invocation backs off."""
    clock = BlockingRetryClock()
    resilience = LlmResiliencePolicy(
        retry=LlmRetryPolicy(
            max_attempts=2,
            backoff_seconds=1.0,
            failure_classes=frozenset({LlmFailureClass.TIMEOUT}),
        ),
        concurrency=LlmConcurrencyPolicy(max_in_flight=1),
    )
    provider = SequencedProvider(
        {
            "primary": [
                LlmTimeoutError(),
                ModelResponse(content="independent"),
                ModelResponse(content="retried"),
            ]
        }
    )
    model = LlmAgentModel(
        _config(resilience=resilience),
        (provider,),
        clock=clock,
    )
    first = create_task(model.complete(_request()))
    await clock.started.wait()

    independent = await model.complete(_request())
    clock.release_sleep.set()
    retried = await first

    assert independent.content == "independent"
    assert retried.content == "retried"
    assert provider.complete_calls == ["primary", "primary", "primary"]


async def test_explicit_fallback_success_expect_primary_then_fallback() -> None:
    """Allowlisted timeout follows the configured logical route order."""
    provider = SequencedProvider(
        {
            "primary": [LlmTimeoutError()],
            "fallback": [ModelResponse(content="fallback-ok")],
        }
    )
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
        ),
        (provider,),
    )

    response = await model.complete(_request())

    assert provider.complete_calls == ["primary", "fallback"]
    assert response.content == "fallback-ok"
    assert response.metadata["fallback_used"] is True
    assert response.metadata["fallback_from"] == "primary"


async def test_all_fallbacks_fail_expect_last_error_with_complete_evidence() -> None:
    """Exhausted explicit chain raises the final typed failure with all attempts."""
    provider = SequencedProvider(
        {
            "primary": [LlmTimeoutError()],
            "fallback": [LlmTransportError()],
        }
    )
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT, LlmFailureClass.TRANSPORT}),
        ),
        (provider,),
    )

    with pytest.raises(LlmTransportError) as raised:
        await model.complete(_request())

    attempts = raised.value.details["attempts"]
    assert isinstance(attempts, tuple)
    assert len(attempts) == 2
    assert provider.complete_calls == ["primary", "fallback"]


async def test_descendant_fallback_uses_descendant_failure_allowlist() -> None:
    """A root policy cannot authorize an edge owned by its failing child route."""
    config = LlmConfig(
        default_model="root",
        profiles={"profile": _profile()},
        models={
            "root": LlmModelRoute(
                profile="profile",
                model="root",
                fallbacks=("b",),
                fallback_on=frozenset({LlmFailureClass.TRANSPORT}),
            ),
            "b": LlmModelRoute(
                profile="profile",
                model="b",
                fallbacks=("c",),
                fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
            ),
            "c": LlmModelRoute(profile="profile", model="c"),
        },
    )
    provider = SequencedProvider(
        {
            "root": [LlmTransportError()],
            "b": [LlmTransportError()],
            "c": [ModelResponse(content="must-not-run")],
        }
    )
    model = LlmAgentModel(config, (provider,))

    with pytest.raises(LlmTransportError):
        await model.complete(_request())

    assert provider.complete_calls == ["root", "b"]
    assert model._candidate_refs_for_failure(
        "root",
        LlmFailureClass.CAPABILITY,
    ) == ("root",)


async def test_unlisted_failure_expect_no_fallback() -> None:
    """Refusal cannot cross providers when only timeout is allowlisted."""
    provider = SequencedProvider(
        {
            "primary": [LlmModelRefusalError()],
            "fallback": [ModelResponse(content="unsafe-fallback")],
        }
    )
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
        ),
        (provider,),
    )

    with pytest.raises(LlmModelRefusalError):
        await model.complete(_request())

    assert provider.complete_calls == ["primary"]


async def test_partial_stream_failure_expect_no_retry_or_fallback() -> None:
    """Once any delta is visible, failure closes the stream without duplication."""
    token = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="partial",
    )
    provider = SequencedProvider(
        complete_outcomes={},
        stream_outcomes={
            "primary": [(token, LlmTimeoutError())],
            "fallback": [(ModelStreamEvent(kind=ModelStreamEventKind.DONE),)],
        },
    )
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
        ),
        (provider,),
    )

    events = [event async for event in model.stream(_request())]

    assert provider.stream_calls == ["primary"]
    assert [event.kind for event in events] == [
        ModelStreamEventKind.TOKEN_DELTA,
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    attempts = _attempts(events[-1].metadata)
    assert attempts[0]["partial_stream_emitted"] is True


async def test_capability_skip_expect_fallback_evidence_before_provider_call() -> None:
    """An incapable primary is skipped only under explicit capability fallback policy."""
    provider = SequencedProvider({"fallback": [ModelResponse(content="ok")]})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.CAPABILITY}),
            fallback_capability=ModelCapability(supports_tools=True),
        ),
        (provider,),
    )
    request = _request(with_tools=True)

    model.validate_request(request)
    response = await model.complete(request)

    assert provider.complete_calls == ["fallback"]
    attempts = _attempts(response.metadata)
    assert attempts[0]["state"] == "skipped_capability"
    assert attempts[0]["capability_skip_reasons"] == ("tools",)


async def test_media_policy_failure_uses_explicit_complete_fallback() -> None:
    """Target media validation is traced before provider I/O and may be allowlisted."""
    policy = PrimaryRejectingMediaPolicy()
    provider = SequencedProvider({"fallback": [ModelResponse(content="ok")]})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.CONFIGURATION}),
        ),
        (provider,),
        media_uri_policy=policy,
    )

    response = await model.complete(_request())

    assert policy.calls == ["primary", "fallback"]
    assert provider.complete_calls == ["fallback"]
    assert _attempts(response.metadata)[0]["failure_stage"] == "media_uri_validation"


async def test_media_policy_failure_uses_explicit_stream_fallback() -> None:
    """The same target-aware media policy governs streaming before any emission."""
    policy = PrimaryRejectingMediaPolicy()
    done = (ModelStreamEvent(kind=ModelStreamEventKind.DONE),)
    provider = SequencedProvider({}, {"fallback": [done]})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.CONFIGURATION}),
        ),
        (provider,),
        media_uri_policy=policy,
    )

    events = [event async for event in model.stream(_request())]

    assert policy.calls == ["primary", "fallback"]
    assert provider.stream_calls == ["fallback"]
    assert _attempts(events[-1].metadata)[0]["failure_stage"] == (
        "media_uri_validation"
    )


async def test_media_policy_unlisted_stream_failure_stops_before_provider() -> None:
    """Without an explicit edge, media authority failure terminates the stream."""
    policy = PrimaryRejectingMediaPolicy()
    provider = SequencedProvider({}, {})
    model = LlmAgentModel(
        _config(),
        (provider,),
        media_uri_policy=policy,
    )

    events = [event async for event in model.stream(_request())]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert provider.stream_calls == []


async def test_exact_cache_miss_store_then_hit_expect_one_provider_attempt() -> None:
    """Complete-only exact cache reports miss/store then hit without replaying tools."""
    cache = RecordingResponseCache(LlmCacheMode.EXACT)
    provider = SequencedProvider(
        {
            "primary": [
                ModelResponse(
                    content="ok",
                    usage=ModelUsage(
                        input_tokens=10,
                        output_tokens=2,
                        total_tokens=12,
                    ),
                )
            ]
        }
    )
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    first = await model.complete(_request())
    second = await model.complete(_request())

    assert provider.complete_calls == ["primary"]
    assert first.metadata["cache_state"] == "stored"
    assert second.metadata["cache_state"] == "hit"
    assert first.usage.total_tokens == 12
    assert second.usage == ModelUsage(
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cached_input_tokens=0,
        cache_write_input_tokens=0,
        cache_write_5m_input_tokens=0,
        cache_write_1h_input_tokens=0,
    )
    assert second.metadata["cache_saved_input_tokens"] == 10
    assert second.metadata["cache_saved_output_tokens"] == 2
    assert second.metadata["cache_saved_total_tokens"] == 12
    assert len(cache.stores) == 1
    assert len(cache.lookups) == 2


async def test_cache_key_provider_and_store_share_one_request_snapshot() -> None:
    """Caller mutation during lookup cannot store a response under an older key."""
    cache = BlockingMissCache()
    provider = RequestEchoProvider()
    source_messages = [ModelMessage.user("original")]
    source_metadata: dict[str, JsonValue] = {"marker": "original"}
    request = ModelRequest(messages=source_messages, metadata=source_metadata)
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )
    pending = create_task(model.complete(request))
    await cache.started.wait()

    source_messages[0] = ModelMessage.user("tampered-source")
    source_metadata["marker"] = "tampered-source"
    cast(dict[str, JsonValue], request.metadata)["marker"] = "tampered-request"
    cache.release_lookup.set()
    first = await pending
    second = await model.complete(
        ModelRequest(
            messages=(ModelMessage.user("original"),),
            metadata={"marker": "original"},
        )
    )

    assert first.content == "seen:original:original"
    assert second.content == "seen:original:original"
    assert provider.complete_calls == ["primary"]


async def test_media_authority_revalidation_precedes_cache_hit() -> None:
    """A cached response cannot bypass a later media-policy revocation."""
    cache = RecordingResponseCache(LlmCacheMode.EXACT)
    policy = RevokingMediaPolicy()
    provider = SequencedProvider({"primary": [ModelResponse(content="cached")]})
    model = LlmAgentModel(
        _config(
            cache_mode=LlmCacheMode.EXACT,
            primary_capability=ModelCapability(
                input_modalities=frozenset({ModelModality.IMAGE})
            ),
        ),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
        media_uri_policy=policy,
    )
    request = ModelRequest(
        messages=(
            ModelMessage.user(
                (
                    ImagePart.from_uri(
                        "https://assets.example.test/x.png",
                        media_type="image/png",
                    ),
                )
            ),
        )
    )
    await model.complete(request)

    with pytest.raises(LlmConfigurationError):
        await model.complete(request)

    assert policy.calls == 2
    assert provider.complete_calls == ["primary"]


async def test_cache_hit_returns_fresh_deep_response_snapshot() -> None:
    """Mutating one returned hit cannot poison the backend receipt for later hits."""
    cache = RecordingResponseCache(LlmCacheMode.EXACT)
    provider = SequencedProvider(
        {
            "primary": [
                ModelResponse(
                    content="ok",
                    structured_output={"nested": {"value": 1}},
                )
            ]
        }
    )
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )
    await model.complete(_request())
    first_hit = await model.complete(_request())
    first_output = cast(dict[str, JsonValue], first_hit.structured_output)
    cast(dict[str, JsonValue], first_output["nested"])["value"] = 999

    second_hit = await model.complete(_request())

    assert second_hit.structured_output == {"nested": {"value": 1}}


async def test_semantic_cache_mode_expect_semantic_backend_selected() -> None:
    """Semantic route selects only the semantic port and exposes semantic input."""
    cache = RecordingResponseCache(LlmCacheMode.SEMANTIC)
    provider = SequencedProvider({"primary": [ModelResponse(content="ok")]})
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.SEMANTIC),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    await model.complete(_request())

    assert cache.lookups[0].mode is LlmCacheMode.SEMANTIC
    assert cache.lookups[0].semantic_input == ("user:hello",)


def test_enabled_cache_without_backend_expect_startup_failure() -> None:
    """Enabled cache mode never degrades silently to uncached production."""
    provider = SequencedProvider({"primary": [ModelResponse(content="ok")]})

    with pytest.raises(LlmCacheConfigurationError):
        LlmAgentModel(_config(cache_mode=LlmCacheMode.EXACT), (provider,))
    with pytest.raises(LlmCacheConfigurationError):
        LlmAgentModel(
            _config(cache_mode=LlmCacheMode.EXACT),
            (provider,),
            response_caches=(RecordingResponseCache(LlmCacheMode.EXACT),),
        )
    with pytest.raises(LlmCacheConfigurationError):
        LlmAgentModel(
            _config(cache_mode=LlmCacheMode.EXACT),
            (provider,),
            cache_scope_resolver=FixedCacheScopeResolver(),
        )


async def test_tool_call_response_expect_not_cached_or_replayed() -> None:
    """Continuation-bearing responses bypass storage and require a fresh provider call."""
    cache = RecordingResponseCache(LlmCacheMode.EXACT)
    tool_response = ModelResponse(
        content="",
        tool_calls=(ModelToolCall("search", {"query": "x"}, "call-1"),),
    )
    provider = SequencedProvider({"primary": [tool_response, tool_response]})
    model = LlmAgentModel(
        _config(
            cache_mode=LlmCacheMode.EXACT,
            primary_capability=ModelCapability(supports_tools=True),
        ),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    first = await model.complete(_request(with_tools=True))
    second = await model.complete(_request(with_tools=True))

    assert provider.complete_calls == ["primary", "primary"]
    assert first.metadata["cache_state"] == "bypassed_tool_calls"
    assert second.metadata["cache_state"] == "bypassed_tool_calls"
    assert cache.stores == []


def test_validate_request_without_capable_allowed_candidate_expect_typed_failure() -> (
    None
):
    """Preflight refuses a fake capability union when fallback is not authorized."""
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
            fallback_capability=ModelCapability(supports_tools=True),
        ),
        (SequencedProvider({}),),
    )

    with pytest.raises(LlmCapabilityError):
        model.validate_request(_request(with_tools=True))


async def test_primary_capability_failure_without_allowlist_expect_no_provider_call() -> (
    None
):
    """Capability mismatch cannot fallback unless capability is explicitly allowlisted."""
    provider = SequencedProvider({"fallback": [ModelResponse(content="unused")]})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
            fallback_capability=ModelCapability(supports_tools=True),
        ),
        (provider,),
    )

    with pytest.raises(LlmCapabilityError) as raised:
        await model.complete(_request(with_tools=True))

    assert provider.complete_calls == []
    assert raised.value.details["cache_state"] == "disabled"


async def test_runtime_missing_provider_expect_typed_complete_failure() -> None:
    """A provider-reported unavailable state remains a typed attempted failure."""
    provider = SequencedProvider({"primary": [LlmProviderUnavailableError()]})
    model = LlmAgentModel(_config(), (provider,))

    with pytest.raises(LlmProviderUnavailableError) as raised:
        await model.complete(_request())

    assert raised.value.details["attempt_ordinal"] == 1


async def test_complete_rate_gate_failure_expect_non_attempt_evidence() -> None:
    """A local admission failure is recorded without claiming an SDK attempt."""
    resilience = LlmResiliencePolicy(
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
        )
    )
    provider = SequencedProvider(
        {"primary": [ModelResponse(content="first"), ModelResponse(content="unused")]}
    )
    model = LlmAgentModel(_config(resilience=resilience), (provider,))
    await model.complete(_request())

    with pytest.raises(LlmRateLimitError) as raised:
        await model.complete(_request())

    attempts = _attempts(raised.value.details)
    assert attempts[0]["actual_attempt"] is False
    assert provider.complete_calls == ["primary"]


async def test_complete_local_rate_retry_waits_without_holding_a_lease() -> None:
    """A typed local admission retry waits, then acquires a fresh provider lease."""
    clock = RecordingClock()
    resilience = LlmResiliencePolicy(
        retry=LlmRetryPolicy(
            max_attempts=2,
            failure_classes=frozenset({LlmFailureClass.RATE_LIMIT}),
        ),
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
        ),
    )
    provider = SequencedProvider(
        {
            "primary": [
                ModelResponse(content="first"),
                ModelResponse(content="second"),
            ]
        }
    )
    model = LlmAgentModel(
        _config(resilience=resilience),
        (provider,),
        clock=clock,
    )
    await model.complete(_request())

    response = await model.complete(_request())

    assert response.content == "second"
    assert response.metadata["retry_count"] == 1
    assert provider.complete_calls == ["primary", "primary"]
    assert clock.sleeps == [10.0]


async def test_stream_pre_emission_retry_expect_second_attempt_done() -> None:
    """A stream setup failure may retry only before any event becomes visible."""
    retry = LlmRetryPolicy(
        max_attempts=2,
        failure_classes=frozenset({LlmFailureClass.TIMEOUT}),
    )
    provider = SequencedProvider(
        {},
        {
            "primary": [
                (LlmTimeoutError(),),
                (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
            ]
        },
    )
    model = LlmAgentModel(_config(retry=retry), (provider,))

    events = [event async for event in model.stream(_request())]

    assert provider.stream_calls == ["primary", "primary"]
    assert [event.kind for event in events] == [ModelStreamEventKind.DONE]
    assert events[0].metadata["retry_count"] == 1


async def test_stream_pre_emission_fallback_expect_ordered_done() -> None:
    """An allowed setup failure can move to fallback before public output."""
    provider = SequencedProvider(
        {},
        {
            "primary": [(LlmTimeoutError(),)],
            "fallback": [(ModelStreamEvent(kind=ModelStreamEventKind.DONE),)],
        },
    )
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
        ),
        (provider,),
    )

    events = [event async for event in model.stream(_request())]

    assert provider.stream_calls == ["primary", "fallback"]
    assert events[0].metadata["fallback_used"] is True


async def test_stream_disabled_primary_expect_explicit_enabled_fallback() -> None:
    """Streaming-disabled failure can fallback only when explicitly allowlisted."""
    config = LlmConfig(
        default_model="primary",
        profiles={
            "disabled": _profile().model_copy(update={"stream_enabled": False}),
            "enabled": _profile(),
        },
        models={
            "primary": LlmModelRoute(
                profile="disabled",
                model="primary",
                fallbacks=("fallback",),
                fallback_on=frozenset({LlmFailureClass.STREAMING_DISABLED}),
            ),
            "fallback": LlmModelRoute(profile="enabled", model="fallback"),
        },
    )
    provider = SequencedProvider(
        {},
        {"fallback": [(ModelStreamEvent(kind=ModelStreamEventKind.DONE),)]},
    )
    model = LlmAgentModel(config, (provider,))

    events = [event async for event in model.stream(_request())]

    assert provider.stream_calls == ["fallback"]
    assert events[0].metadata["fallback_used"] is True


async def test_stream_without_done_expect_successful_early_completion_metadata() -> (
    None
):
    """A provider that ends after a token closes its circuit lease once."""
    provider = SequencedProvider(
        {},
        {
            "primary": [
                (
                    ModelStreamEvent(
                        kind=ModelStreamEventKind.TOKEN_DELTA,
                        token_delta="only",
                    ),
                )
            ]
        },
    )
    model = LlmAgentModel(_config(), (provider,))

    events = [event async for event in model.stream(_request())]

    assert events[0].kind is ModelStreamEventKind.TOKEN_DELTA


async def test_stream_all_capabilities_skipped_expect_terminal_evidence() -> None:
    """An explicit capability chain with no capable route terminates without I/O."""
    provider = SequencedProvider({}, {})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.CAPABILITY}),
        ),
        (provider,),
    )

    events = [event async for event in model.stream(_request(with_tools=True))]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert provider.stream_calls == []
    assert len(_attempts(events[-1].metadata)) == 2


async def test_stream_primary_capability_unlisted_expect_immediate_terminal() -> None:
    """Unlisted primary capability failure cannot inspect fallback providers."""
    provider = SequencedProvider({}, {})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
            fallback_capability=ModelCapability(supports_tools=True),
        ),
        (provider,),
    )

    events = [event async for event in model.stream(_request(with_tools=True))]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert events[0].error is not None
    assert events[0].error.code == "llm_capability_insufficient"
    assert provider.stream_calls == []


async def test_stream_rate_gate_failure_expect_typed_terminal_without_attempt() -> None:
    """Stream admission failure is terminal when rate-limit fallback is not configured."""
    resilience = LlmResiliencePolicy(
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
        )
    )
    provider = SequencedProvider(
        {},
        {
            "primary": [
                (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
                (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
            ]
        },
    )
    model = LlmAgentModel(_config(resilience=resilience), (provider,))
    first_events = [event async for event in model.stream(_request())]
    assert first_events[0].kind is ModelStreamEventKind.DONE

    events = [event async for event in model.stream(_request())]

    assert [event.kind for event in events] == [
        ModelStreamEventKind.ERROR,
        ModelStreamEventKind.DONE,
    ]
    assert events[0].error is not None
    assert events[0].error.code == "llm_rate_limited"


async def test_stream_local_rate_retry_waits_before_provider_emission() -> None:
    """A pre-emission local rate failure can retry after its typed wait interval."""
    clock = RecordingClock()
    resilience = LlmResiliencePolicy(
        retry=LlmRetryPolicy(
            max_attempts=2,
            failure_classes=frozenset({LlmFailureClass.RATE_LIMIT}),
        ),
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
        ),
    )
    done = (ModelStreamEvent(kind=ModelStreamEventKind.DONE),)
    provider = SequencedProvider({}, {"primary": [done, done]})
    model = LlmAgentModel(
        _config(resilience=resilience),
        (provider,),
        clock=clock,
    )
    _ = [event async for event in model.stream(_request())]

    events = [event async for event in model.stream(_request())]

    assert events[-1].kind is ModelStreamEventKind.DONE
    assert events[-1].metadata["retry_count"] == 1
    assert provider.stream_calls == ["primary", "primary"]
    assert clock.sleeps == [10.0]


def test_convergent_fallback_graph_expect_each_candidate_once() -> None:
    """Depth-first ordered traversal de-duplicates convergent fallback refs."""
    config = LlmConfig(
        default_model="primary",
        profiles={"profile": _profile()},
        models={
            "primary": LlmModelRoute(
                profile="profile",
                model="primary",
                fallbacks=("a", "b"),
                fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
            ),
            "a": LlmModelRoute(
                profile="profile",
                model="a",
                fallbacks=("b",),
                fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
            ),
            "b": LlmModelRoute(profile="profile", model="b"),
        },
    )
    model = LlmAgentModel(config, (SequencedProvider({}),))

    assert model._candidate_refs("primary") == ("primary", "a", "b")
    assert model._candidate_refs_for_failure(
        "primary",
        LlmFailureClass.TIMEOUT,
    ) == ("primary", "a", "b")


def test_cache_registry_expect_disabled_or_duplicate_backends_rejected() -> None:
    """Each enabled cache mode has exactly one replaceable implementation."""
    provider = SequencedProvider({})
    with pytest.raises(LlmCacheConfigurationError):
        LlmAgentModel(
            _config(),
            (provider,),
            response_caches=(RecordingResponseCache(LlmCacheMode.DISABLED),),
        )
    with pytest.raises(LlmCacheConfigurationError):
        LlmAgentModel(
            _config(),
            (provider,),
            response_caches=(
                RecordingResponseCache(LlmCacheMode.EXACT),
                RecordingResponseCache(LlmCacheMode.EXACT),
            ),
        )


async def test_cache_runtime_corruption_expect_typed_fail_closed() -> None:
    """Missing or continuation-bearing runtime cache state cannot be consumed."""
    cache = RecordingResponseCache(LlmCacheMode.EXACT)
    provider = SequencedProvider({"primary": [ModelResponse(content="ok")]})
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (provider,),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )
    first = await model.complete(_request())
    assert first.metadata["cache_state"] == "stored"
    digest = cache.lookups[0].key.digest
    cache.entries[digest] = LlmCachedResponse(
        ModelResponse(
            content="",
            tool_calls=(ModelToolCall("search", {}, "call"),),
        )
    )

    with pytest.raises(LlmCacheConfigurationError):
        await model.complete(_request())


async def test_cache_receipt_mutated_after_construction_expect_revalidated() -> None:
    """A backend-held receipt cannot bypass validation through later mutation."""
    cached = LlmCachedResponse(ModelResponse(content="safe"))
    object.__setattr__(cached.response, "content", 123)
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (SequencedProvider({}),),
        response_caches=(UntrustedResponseCache(lookup_value=cached),),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    with pytest.raises(LlmCacheConfigurationError):
        await model.complete(_request())


@pytest.mark.parametrize(
    "cache",
    [
        UntrustedResponseCache(lookup_error=True),
        UntrustedResponseCache(typed_lookup_error=True),
        UntrustedResponseCache(lookup_value=object()),
        UntrustedResponseCache(store_error=True),
        UntrustedResponseCache(typed_store_error=True),
    ],
)
async def test_untrusted_cache_failures_expect_typed_boundary(
    cache: ILLMResponseCache,
) -> None:
    """Backend exceptions and malformed hits never leak their runtime types."""
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (SequencedProvider({"primary": [ModelResponse(content="ok")]}),),
        response_caches=(cache,),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    with pytest.raises(LlmCacheConfigurationError):
        await model.complete(_request())


async def test_untrusted_cache_scope_failure_expect_typed_boundary() -> None:
    """A failing tenant/safety resolver cannot escape as an application exception."""
    model = LlmAgentModel(
        _config(cache_mode=LlmCacheMode.EXACT),
        (SequencedProvider({"primary": [ModelResponse(content="ok")]}),),
        response_caches=(RecordingResponseCache(LlmCacheMode.EXACT),),
        cache_scope_resolver=FailingCacheScopeResolver(),
    )

    with pytest.raises(LlmCacheConfigurationError):
        await model.complete(_request())


async def test_cache_lookup_failure_uses_current_route_explicit_fallback() -> None:
    """A pre-provider cache failure may cross only an explicitly authorized edge."""
    provider = SequencedProvider({"fallback": [ModelResponse(content="fallback-ok")]})
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.CACHE}),
            cache_mode=LlmCacheMode.EXACT,
        ),
        (provider,),
        response_caches=(UntrustedResponseCache(lookup_error=True),),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    response = await model.complete(_request())

    assert provider.complete_calls == ["fallback"]
    assert _attempts(response.metadata)[0]["failure_stage"] == "cache_lookup"
    selections = cast(
        Sequence[Mapping[str, JsonValue]],
        response.metadata["cache_selections"],
    )
    assert selections[0]["state"] == "failed"


async def test_cache_store_failure_never_replays_a_billable_model_attempt() -> None:
    """A post-success cache failure is traced but cannot trigger a second model bill."""
    provider = SequencedProvider(
        {
            "primary": [
                ModelResponse(
                    content="primary-ok",
                    usage=ModelUsage(
                        input_tokens=10,
                        output_tokens=2,
                        total_tokens=12,
                    ),
                )
            ],
            "fallback": [ModelResponse(content="must-not-run")],
        }
    )
    model = LlmAgentModel(
        _config(
            root_fallbacks=("fallback",),
            fallback_on=frozenset({LlmFailureClass.CACHE}),
            cache_mode=LlmCacheMode.EXACT,
        ),
        (provider,),
        response_caches=(UntrustedResponseCache(store_error=True),),
        cache_scope_resolver=FixedCacheScopeResolver(),
    )

    with pytest.raises(LlmCacheConfigurationError) as raised:
        await model.complete(_request())

    assert provider.complete_calls == ["primary"]
    attempt = _attempts(raised.value.details)[0]
    assert attempt["failure_stage"] == "cache_store"
    assert attempt["fallback_suppressed"] == "provider_success"
    assert raised.value.model_usage == ModelUsage(
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
    )
    assert raised.value.model_metadata["model_ref"] == "primary"


def test_capability_reason_matrix_expect_modality_output_and_schema_evidence() -> None:
    """Candidate validation records every missing request capability without bodies."""
    model = LlmAgentModel(_config(), (SequencedProvider({}),))
    target = model._target("primary")
    request = ModelRequest(
        messages=(
            ModelMessage.user(
                (ImagePart.from_bytes(b"image", media_type="image/png"),)
            ),
        ),
        structured_output=StructuredOutputSpec(
            JsonSchemaConstraint(schema={"type": "object"})
        ),
    )
    target = replace(
        target,
        route=target.route.model_copy(
            update={
                "capability": ModelCapability(
                    input_modalities=frozenset({ModelModality.TEXT}),
                    output_modalities=frozenset({ModelModality.IMAGE}),
                )
            }
        ),
    )

    reasons = model._capability_reasons(target, request)

    assert reasons == ("input:image", "output:text", "structured_output")


def test_selection_evidence_without_reasons_expect_no_empty_reason_field() -> None:
    """Non-capability selections do not fabricate an empty reason payload."""
    model = LlmAgentModel(_config(), (SequencedProvider({}),))
    target = model._target("primary")

    evidence = model._selection_evidence(target, target, "selected")

    assert "capability_skip_reasons" not in evidence
