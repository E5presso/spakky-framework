"""Resilient operator-catalog implementation of the Agent model port."""

from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import replace
from typing import cast, override

from spakky.agent import (
    IAgentModel,
    JsonObject,
    JsonValue,
    ModelCapability,
    ModelError,
    ModelModality,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.cache import (
    ILLMCacheScopeResolver,
    ILLMResponseCache,
    LlmCacheKeyBuilder,
    LlmCachedResponse,
    LlmCacheLookup,
    LlmCacheMode,
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
    LlmModelSelectionError,
    LlmProviderUnavailableError,
    LlmStreamingDisabledError,
)
from spakky.plugins.llm.media import ILLMMediaUriPolicy, PublicLlmMediaUriPolicy
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    error_event,
    failure_code,
    routing_metadata,
)
from spakky.plugins.llm.resilience import (
    ILLMClock,
    LlmAttemptLease,
    LlmResilienceController,
)


type _Evidence = dict[str, JsonValue]


@Pod()
class LlmAgentModel(IAgentModel):
    """Resolve opaque routes with explicit cache, retry, and fallback policies."""

    __default_model: str
    __models: dict[str, LlmModelRoute]
    __profiles: dict[str, LlmProfile]
    __providers: dict[LlmProviderApi, ILLMProvider]
    __cache_backends: dict[LlmCacheMode, ILLMResponseCache]
    __cache_scope_resolver: ILLMCacheScopeResolver | None
    __media_uri_policy: ILLMMediaUriPolicy
    __resilience: LlmResilienceController

    def __init__(
        self,
        config: LlmConfig,
        providers: tuple[ILLMProvider, ...],
        response_caches: tuple[ILLMResponseCache, ...] = (),
        cache_scope_resolver: ILLMCacheScopeResolver | None = None,
        clock: ILLMClock | None = None,
        media_uri_policy: ILLMMediaUriPolicy | None = None,
    ) -> None:
        self.__default_model = config.default_model
        self.__models = {
            model_ref: route.model_copy(deep=True)
            for model_ref, route in config.models.items()
        }
        self.__profiles = {
            name: profile.model_copy(deep=True)
            for name, profile in config.profiles.items()
        }
        self.__providers = self._provider_registry(providers)
        configured_apis = {profile.api for profile in self.__profiles.values()}
        if not configured_apis.issubset(self.__providers):
            raise LlmConfigurationError
        self.__cache_backends = self._cache_registry(response_caches)
        self.__cache_scope_resolver = cache_scope_resolver
        self._validate_cache_dependencies()
        self.__resilience = LlmResilienceController(clock)
        self.__media_uri_policy = (
            media_uri_policy
            if media_uri_policy is not None
            else PublicLlmMediaUriPolicy()
        )

    @property
    @override
    def capability(self) -> ModelCapability:
        """Return the configured default route capability."""
        return self._default_target().route.capability

    @override
    def capability_for(
        self,
        selection: ModelSelection | None = None,
    ) -> ModelCapability:
        """Return the exact selected primary route capability."""
        return self._resolve_target(selection).route.capability

    @override
    def validate_request(self, request: ModelRequest) -> None:
        """Accept when any explicitly reachable candidate satisfies the request."""
        root = self._resolve_target(request.model_selection)
        candidates = (
            self._candidate_refs_for_failure(
                root.model_ref,
                LlmFailureClass.CAPABILITY,
            )
            if LlmFailureClass.CAPABILITY in root.route.fallback_on
            else (root.model_ref,)
        )
        for model_ref in candidates:
            if len(self._capability_reasons(self._target(model_ref), request)) == 0:
                return
        raise LlmCapabilityError

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Complete through bounded retries and explicitly ordered fallbacks."""
        request = request.snapshot()
        root = self._resolve_target(request.model_selection)
        candidates = self._candidate_refs(root.model_ref)
        attempts: list[_Evidence] = []
        cache_selections: list[_Evidence] = []
        attempt_ordinal = 0
        retry_count = 0
        last_error: AbstractLlmError | None = None
        last_target = root
        for model_ref in candidates:
            target = self._target(model_ref)
            last_target = target
            capability_reasons = self._capability_reasons(target, request)
            if len(capability_reasons) > 0:
                capability_error = LlmCapabilityError(
                    details={"capability_skip_reasons": capability_reasons}
                )
                attempts.append(
                    self._selection_evidence(
                        root,
                        target,
                        "skipped_capability",
                        capability_reasons=capability_reasons,
                    )
                )
                last_error = capability_error
                if not self._fallback_allowed(target, capability_error):
                    break
                continue

            try:
                await self.__media_uri_policy.validate(target, request)
            except AbstractLlmError as error:
                last_error = error
                evidence = self._failure_evidence(root, target, error)
                evidence["failure_stage"] = "media_uri_validation"
                attempts.append(evidence)
                if not self._fallback_allowed(target, error):
                    break
                continue

            try:
                cached, cache_query = await self._lookup_cache(
                    target,
                    request,
                    cache_selections,
                )
            except AbstractLlmError as error:
                last_error = error
                self._record_cache_failure(
                    target,
                    cache_selections,
                    error,
                    stage="lookup",
                )
                evidence = self._failure_evidence(root, target, error)
                evidence["failure_stage"] = "cache_lookup"
                attempts.append(evidence)
                if not self._fallback_allowed(target, error):
                    break
                continue
            if cached is not None:
                metadata = {
                    **self._metadata(
                        root,
                        target,
                        attempts,
                        cache_selections,
                        retry_count,
                    ),
                    **self._cache_saved_usage(cached.response.usage),
                }
                return replace(
                    deepcopy(cached.response),
                    usage=ModelUsage(
                        input_tokens=0,
                        output_tokens=0,
                        total_tokens=0,
                        cached_input_tokens=0,
                        cache_write_input_tokens=0,
                        cache_write_5m_input_tokens=0,
                        cache_write_1h_input_tokens=0,
                    ),
                    metadata={**cached.response.metadata, **metadata},
                )

            provider = self._provider_for(target)
            retry_policy = target.profile.resilience.retry
            profile_attempt = 1
            while True:
                lease: LlmAttemptLease | None = None
                try:
                    lease = await self.__resilience.acquire(
                        target.profile_name,
                        target.profile.resilience,
                    )
                    attempt_ordinal += 1
                    response = await provider.complete(target, request)
                except AbstractLlmError as error:
                    last_error = error
                    if lease is not None:
                        await self.__resilience.record_failure(
                            lease,
                            target.profile.resilience.circuit,
                            error.failure_class,
                        )
                    evidence = self._failure_evidence(
                        root,
                        target,
                        error,
                        attempt_ordinal=(
                            attempt_ordinal if lease is not None else None
                        ),
                        profile_attempt=profile_attempt,
                    )
                    attempts.append(evidence)
                    if (
                        profile_attempt < retry_policy.max_attempts
                        and error.failure_class in retry_policy.failure_classes
                    ):
                        retry_count += 1
                        if lease is not None:
                            await self.__resilience.release(lease)
                        evidence[
                            "retry_delay_seconds"
                        ] = await self.__resilience.retry_delay(
                            retry_policy,
                            profile_attempt,
                            error,
                        )
                        profile_attempt += 1
                        continue
                    break
                else:
                    await self.__resilience.record_success(
                        lease,
                        target.profile.resilience.circuit,
                    )
                    attempts.append(
                        self._success_evidence(
                            root,
                            target,
                            attempt_ordinal,
                            profile_attempt,
                        )
                    )
                    try:
                        cache_state = await self._store_cache(
                            target,
                            cache_query,
                            response,
                            cache_selections,
                        )
                    except AbstractLlmError as error:
                        self._record_cache_failure(
                            target,
                            cache_selections,
                            error,
                            stage="store",
                        )
                        attempts[-1].update(
                            {
                                **self._failure_fields(error, emitted=False),
                                "failure_stage": "cache_store",
                                "fallback_suppressed": "provider_success",
                            }
                        )
                        annotated = self._annotated_error(
                            error,
                            root,
                            target,
                            attempts,
                            cache_selections,
                            retry_count,
                        )
                        annotated.attach_model_receipt(
                            response.usage,
                            {
                                **routing_metadata(target),
                                **annotated.details,
                            },
                        )
                        raise annotated
                    metadata = self._metadata(
                        root,
                        target,
                        attempts,
                        cache_selections,
                        retry_count,
                        cache_state=cache_state,
                    )
                    return replace(
                        response,
                        metadata={**response.metadata, **metadata},
                    )
                finally:
                    if lease is not None:
                        await self.__resilience.release(lease)
            if last_error is not None and not self._fallback_allowed(
                target,
                last_error,
            ):
                break

        final_error = last_error or LlmCapabilityError()
        raise self._annotated_error(
            final_error,
            root,
            last_target,
            attempts,
            cache_selections,
            retry_count,
        )

    @override
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Stream with pre-emission retry/fallback and no response-cache replay."""
        return self._stream(request.snapshot())

    async def _stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        try:
            root = self._resolve_target(request.model_selection)
        except LlmModelSelectionError as error:
            model_ref = self._requested_model_ref(request.model_selection)
            metadata = {
                "model_ref": model_ref,
                "failure_class": error.failure_class.value,
                "cache_state": "bypassed_streaming",
            }
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(
                    code="llm_model_selection_invalid",
                    message=error.message,
                    metadata=metadata,
                ),
                metadata=metadata,
            )
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.DONE,
                metadata=metadata,
            )
            return

        candidates = self._candidate_refs(root.model_ref)
        attempts: list[_Evidence] = []
        cache_selections: list[_Evidence] = [
            {
                "model_ref": root.model_ref,
                "mode": root.route.cache.mode.value,
                "state": "bypassed_streaming",
            }
        ]
        attempt_ordinal = 0
        retry_count = 0
        last_error: AbstractLlmError | None = None
        last_target = root
        for model_ref in candidates:
            target = self._target(model_ref)
            last_target = target
            capability_reasons = self._capability_reasons(target, request)
            if len(capability_reasons) > 0:
                capability_error = LlmCapabilityError(
                    details={"capability_skip_reasons": capability_reasons}
                )
                attempts.append(
                    self._selection_evidence(
                        root,
                        target,
                        "skipped_capability",
                        capability_reasons=capability_reasons,
                    )
                )
                last_error = capability_error
                if not self._fallback_allowed(target, capability_error):
                    break
                continue
            if not target.profile.stream_enabled:
                stream_error = LlmStreamingDisabledError()
                attempts.append(self._failure_evidence(root, target, stream_error))
                if not self._fallback_allowed(target, stream_error):
                    last_error = stream_error
                    break
                last_error = stream_error
                continue
            try:
                await self.__media_uri_policy.validate(target, request)
            except AbstractLlmError as error:
                last_error = error
                evidence = self._failure_evidence(root, target, error)
                evidence["failure_stage"] = "media_uri_validation"
                attempts.append(evidence)
                if not self._fallback_allowed(target, error):
                    break
                continue
            provider = self._provider_for(target)

            retry_policy = target.profile.resilience.retry
            profile_attempt = 1
            while True:
                lease: LlmAttemptLease | None = None
                emitted = False
                attempt_evidence: _Evidence | None = None
                try:
                    lease = await self.__resilience.acquire(
                        target.profile_name,
                        target.profile.resilience,
                    )
                    attempt_ordinal += 1
                    attempt_evidence = self._success_evidence(
                        root,
                        target,
                        attempt_ordinal,
                        profile_attempt,
                        state="in_progress",
                    )
                    attempts.append(attempt_evidence)
                    completed = False
                    async for event in provider.stream(target, request):
                        if event.kind is ModelStreamEventKind.DONE:
                            await self.__resilience.record_success(
                                lease,
                                target.profile.resilience.circuit,
                            )
                            attempt_evidence["state"] = "success"
                            completed = True
                        metadata = self._metadata(
                            root,
                            target,
                            attempts,
                            cache_selections,
                            retry_count,
                        )
                        emitted = True
                        yield replace(event, metadata={**event.metadata, **metadata})
                    if not completed:
                        await self.__resilience.record_success(
                            lease,
                            target.profile.resilience.circuit,
                        )
                        attempt_evidence["state"] = "success"
                    return
                except AbstractLlmError as error:
                    last_error = error
                    if lease is not None:
                        await self.__resilience.record_failure(
                            lease,
                            target.profile.resilience.circuit,
                            error.failure_class,
                        )
                    if attempt_evidence is None:
                        attempt_evidence = self._failure_evidence(
                            root,
                            target,
                            error,
                            profile_attempt=profile_attempt,
                        )
                        attempts.append(attempt_evidence)
                    else:
                        attempt_evidence.update(
                            self._failure_fields(error, emitted=emitted)
                        )
                    if emitted:
                        metadata = self._metadata(
                            root,
                            target,
                            attempts,
                            cache_selections,
                            retry_count,
                        )
                        yield error_event(error, target, metadata)
                        yield done_event(target, None, None, metadata)
                        return
                    if (
                        profile_attempt < retry_policy.max_attempts
                        and error.failure_class in retry_policy.failure_classes
                    ):
                        retry_count += 1
                        if lease is not None:
                            await self.__resilience.release(lease)
                        attempt_evidence[
                            "retry_delay_seconds"
                        ] = await self.__resilience.retry_delay(
                            retry_policy,
                            profile_attempt,
                            error,
                        )
                        profile_attempt += 1
                        continue
                    break
                finally:
                    if lease is not None:
                        await self.__resilience.release(lease)
            if last_error is not None and not self._fallback_allowed(
                target,
                last_error,
            ):
                break

        final_error = last_error or LlmCapabilityError()
        metadata = self._metadata(
            root,
            last_target,
            attempts,
            cache_selections,
            retry_count,
        )
        yield error_event(final_error, last_target, metadata)
        yield done_event(last_target, None, None, metadata)

    def _default_target(self) -> LlmModelTarget:
        return self._target(self.__default_model)

    def _resolve_target(
        self,
        selection: ModelSelection | None,
    ) -> LlmModelTarget:
        return self._target(self._requested_model_ref(selection))

    def _requested_model_ref(self, selection: ModelSelection | None) -> str:
        if selection is None:
            return self.__default_model
        return selection.model_ref.strip()

    def _target(self, model_ref: str) -> LlmModelTarget:
        route = self.__models.get(model_ref)
        if route is None:
            raise LlmModelSelectionError
        profile = self.__profiles.get(route.profile)
        if profile is None:
            raise LlmModelSelectionError
        return LlmModelTarget(
            model_ref=model_ref,
            profile_name=route.profile,
            profile=profile,
            route=route,
        )

    def _candidate_refs(self, model_ref: str) -> tuple[str, ...]:
        ordered: list[str] = []
        visited: set[str] = set()

        def visit(candidate_ref: str) -> None:
            if candidate_ref in visited:
                return
            visited.add(candidate_ref)
            ordered.append(candidate_ref)
            for fallback_ref in self.__models[candidate_ref].fallbacks:
                visit(fallback_ref)

        visit(model_ref)
        return tuple(ordered)

    def _candidate_refs_for_failure(
        self,
        model_ref: str,
        failure_class: LlmFailureClass,
    ) -> tuple[str, ...]:
        """Traverse only edges whose owning route explicitly allows the failure."""
        ordered: list[str] = []
        visited: set[str] = set()

        def visit(candidate_ref: str) -> None:
            if candidate_ref in visited:
                return
            visited.add(candidate_ref)
            ordered.append(candidate_ref)
            route = self.__models[candidate_ref]
            if failure_class not in route.fallback_on:
                return
            for fallback_ref in route.fallbacks:
                visit(fallback_ref)

        visit(model_ref)
        return tuple(ordered)

    def _provider_for(self, target: LlmModelTarget) -> ILLMProvider:
        provider = self.__providers.get(target.profile.api)
        if provider is None:
            raise LlmProviderUnavailableError
        return provider

    def _provider_registry(
        self,
        providers: tuple[ILLMProvider, ...],
    ) -> dict[LlmProviderApi, ILLMProvider]:
        candidates: dict[LlmProviderApi, list[ILLMProvider]] = {}
        for provider in providers:
            if len(provider.apis) == 0:
                raise LlmConfigurationError
            for api in provider.apis:
                candidates.setdefault(api, []).append(provider)
        registry: dict[LlmProviderApi, ILLMProvider] = {}
        for api, implementations in candidates.items():
            replacements = tuple(
                provider for provider in implementations if not provider.is_default
            )
            if len(replacements) > 1:
                raise LlmConfigurationError
            if len(replacements) == 1:
                registry[api] = replacements[0]
                continue
            defaults = tuple(
                provider for provider in implementations if provider.is_default
            )
            if len(defaults) != 1:
                raise LlmConfigurationError
            registry[api] = defaults[0]
        return registry

    def _cache_registry(
        self,
        caches: tuple[ILLMResponseCache, ...],
    ) -> dict[LlmCacheMode, ILLMResponseCache]:
        registry: dict[LlmCacheMode, ILLMResponseCache] = {}
        for cache in caches:
            if cache.mode is LlmCacheMode.DISABLED or cache.mode in registry:
                raise LlmCacheConfigurationError
            registry[cache.mode] = cache
        return registry

    def _validate_cache_dependencies(self) -> None:
        enabled_modes = {
            route.cache.mode
            for route in self.__models.values()
            if route.cache.mode is not LlmCacheMode.DISABLED
        }
        if len(enabled_modes) == 0:
            return
        if self.__cache_scope_resolver is None or not enabled_modes.issubset(
            self.__cache_backends
        ):
            raise LlmCacheConfigurationError

    async def _lookup_cache(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
        selections: list[_Evidence],
    ) -> tuple[LlmCachedResponse | None, LlmCacheLookup | None]:
        policy = target.route.cache
        if policy.mode is LlmCacheMode.DISABLED:
            selections.append(
                {
                    "model_ref": target.model_ref,
                    "mode": policy.mode.value,
                    "state": "disabled",
                }
            )
            return None, None
        resolver = cast(
            ILLMCacheScopeResolver,
            self.__cache_scope_resolver,
        )  # constructor invariant: every enabled mode requires a resolver
        backend = self.__cache_backends[policy.mode]
        try:
            query = LlmCacheKeyBuilder.build(
                policy,
                resolver.resolve(request),
                target,
                request,
            )
            cached = await backend.lookup(query)
        except AbstractLlmError:
            raise
        except Exception as error:
            raise LlmCacheConfigurationError from error
        if cached is not None and not isinstance(cached, LlmCachedResponse):
            raise LlmCacheConfigurationError
        if cached is not None:
            cached = LlmCachedResponse(cached.response)
        state = "hit" if cached is not None else "miss"
        selections.append(
            {
                "model_ref": target.model_ref,
                "mode": policy.mode.value,
                "state": state,
                "lookup_state": state,
                "key_digest": query.key.digest,
            }
        )
        if cached is not None and len(cached.response.tool_calls) > 0:
            raise LlmCacheConfigurationError
        return cached, query

    async def _store_cache(
        self,
        target: LlmModelTarget,
        query: LlmCacheLookup | None,
        response: ModelResponse,
        selections: list[_Evidence],
    ) -> str:
        if query is None:
            return "disabled"
        if len(response.tool_calls) > 0:
            selections[-1]["state"] = "bypassed_tool_calls"
            selections[-1]["store_state"] = "bypassed_tool_calls"
            return "bypassed_tool_calls"
        backend = self.__cache_backends[query.mode]
        try:
            await backend.store(
                query,
                LlmCachedResponse(response=response),
                ttl_seconds=target.route.cache.ttl_seconds,
            )
        except AbstractLlmError:
            raise
        except Exception as error:
            raise LlmCacheConfigurationError from error
        selections[-1]["state"] = "stored"
        selections[-1]["store_state"] = "stored"
        return "stored"

    def _capability_reasons(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> tuple[str, ...]:
        capability = target.route.capability
        reasons: list[str] = []
        for modality in sorted(
            request.required_input_modalities(), key=lambda item: item.value
        ):
            if modality not in capability.input_modalities:
                reasons.append(f"input:{modality.value}")
        if ModelModality.TEXT not in capability.output_modalities:
            reasons.append("output:text")
        if request.tool_calling is not None and not capability.supports_tools:
            reasons.append("tools")
        if (
            request.structured_output is not None
            and not capability.supports_structured_output
        ):
            reasons.append("structured_output")
        return tuple(reasons)

    @staticmethod
    def _cache_saved_usage(usage: ModelUsage) -> JsonObject:
        values = {
            "cache_saved_input_tokens": usage.input_tokens,
            "cache_saved_output_tokens": usage.output_tokens,
            "cache_saved_total_tokens": usage.total_tokens,
        }
        return {key: value for key, value in values.items() if value is not None}

    def _record_cache_failure(
        self,
        target: LlmModelTarget,
        selections: list[_Evidence],
        error: AbstractLlmError,
        *,
        stage: str,
    ) -> None:
        evidence: _Evidence = {
            "model_ref": target.model_ref,
            "mode": target.route.cache.mode.value,
            "state": "failed",
            f"{stage}_state": "failed",
            "failure_code": failure_code(error),
            "failure_class": error.failure_class.value,
        }
        if (
            len(selections) > 0
            and selections[-1].get("model_ref") == target.model_ref
            and selections[-1].get("mode") == target.route.cache.mode.value
        ):
            selections[-1].update(evidence)
            return
        selections.append(evidence)

    def _fallback_allowed(
        self,
        target: LlmModelTarget,
        error: AbstractLlmError,
    ) -> bool:
        return (
            len(target.route.fallbacks) > 0
            and error.failure_class in target.route.fallback_on
        )

    def _selection_evidence(
        self,
        root: LlmModelTarget,
        target: LlmModelTarget,
        state: str,
        *,
        capability_reasons: tuple[str, ...] = (),
    ) -> _Evidence:
        evidence = self._base_evidence(root, target)
        evidence.update(
            {
                "actual_attempt": False,
                "state": state,
                "circuit_state": self.__resilience.circuit_state(
                    target.profile_name
                ).value,
            }
        )
        if len(capability_reasons) > 0:
            evidence["capability_skip_reasons"] = capability_reasons
        return evidence

    def _success_evidence(
        self,
        root: LlmModelTarget,
        target: LlmModelTarget,
        attempt_ordinal: int,
        profile_attempt: int,
        *,
        state: str = "success",
    ) -> _Evidence:
        evidence = self._base_evidence(root, target)
        evidence.update(
            {
                "actual_attempt": True,
                "attempt_ordinal": attempt_ordinal,
                "profile_attempt": profile_attempt,
                "state": state,
                "circuit_state": self.__resilience.circuit_state(
                    target.profile_name
                ).value,
            }
        )
        return evidence

    def _failure_evidence(
        self,
        root: LlmModelTarget,
        target: LlmModelTarget,
        error: AbstractLlmError,
        *,
        attempt_ordinal: int | None = None,
        profile_attempt: int | None = None,
    ) -> _Evidence:
        evidence = self._base_evidence(root, target)
        evidence.update(
            {
                "actual_attempt": attempt_ordinal is not None,
                "state": "failure",
                "circuit_state": self.__resilience.circuit_state(
                    target.profile_name
                ).value,
                **self._failure_fields(error, emitted=False),
            }
        )
        if attempt_ordinal is not None:
            evidence["attempt_ordinal"] = attempt_ordinal
        if profile_attempt is not None:
            evidence["profile_attempt"] = profile_attempt
        return evidence

    def _failure_fields(
        self,
        error: AbstractLlmError,
        *,
        emitted: bool,
    ) -> _Evidence:
        fields: _Evidence = {
            "state": "failure",
            "failure_code": failure_code(error),
            "failure_class": error.failure_class.value,
            "partial_stream_emitted": emitted,
        }
        if error.retry_after_seconds is not None:
            fields["retry_after_seconds"] = error.retry_after_seconds
        return fields

    def _base_evidence(
        self,
        root: LlmModelTarget,
        target: LlmModelTarget,
    ) -> _Evidence:
        fallback_used = target.model_ref != root.model_ref
        return {
            "model_ref": target.model_ref,
            "profile": target.profile_name,
            "provider": target.profile.provider,
            "model": target.model,
            "sdk_max_retries": target.profile.max_retries,
            "orchestration_max_attempts": (
                target.profile.resilience.retry.max_attempts
            ),
            "fallback_used": fallback_used,
            "fallback_from": root.model_ref if fallback_used else None,
        }

    def _metadata(
        self,
        root: LlmModelTarget,
        target: LlmModelTarget,
        attempts: list[_Evidence],
        cache_selections: list[_Evidence],
        retry_count: int,
        *,
        cache_state: str | None = None,
    ) -> JsonObject:
        fallback_used = target.model_ref != root.model_ref
        actual_attempts = sum(
            1 for evidence in attempts if evidence.get("actual_attempt") is True
        )
        effective_cache_state = cache_state
        if effective_cache_state is None:
            effective_cache_state = (
                str(cache_selections[-1]["state"])
                if len(cache_selections) > 0
                else "disabled"
            )
        return {
            "attempted_model_ref": target.model_ref,
            "attempted_profile": target.profile_name,
            "attempted_provider": target.profile.provider,
            "attempt_ordinal": actual_attempts,
            "attempts": tuple(dict(evidence) for evidence in attempts),
            "fallback_used": fallback_used,
            "fallback_from": root.model_ref if fallback_used else None,
            "retry_count": retry_count,
            "sdk_max_retries": target.profile.max_retries,
            "orchestration_max_attempts": (
                target.profile.resilience.retry.max_attempts
            ),
            "circuit_state": self.__resilience.circuit_state(target.profile_name).value,
            "cache_state": effective_cache_state,
            "cache_mode": target.route.cache.mode.value,
            "cache_selections": tuple(dict(item) for item in cache_selections),
        }

    def _annotated_error(
        self,
        error: AbstractLlmError,
        root: LlmModelTarget,
        target: LlmModelTarget,
        attempts: list[_Evidence],
        cache_selections: list[_Evidence],
        retry_count: int,
    ) -> AbstractLlmError:
        error.annotate(
            self._metadata(
                root,
                target,
                attempts,
                cache_selections,
                retry_count,
            )
        )
        return error
