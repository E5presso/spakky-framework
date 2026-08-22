"""Operator-catalog multi-provider implementation of the agent model port."""

from collections.abc import AsyncIterator
from typing import override

from spakky.agent import (
    IAgentModel,
    ModelCapability,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
    ModelStreamEventKind,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.config import (
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
)
from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmConfigurationError,
    LlmModelSelectionError,
    LlmProviderUnavailableError,
    LlmStreamingDisabledError,
)
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    error_event,
)


@Pod()
class LlmAgentModel(IAgentModel):
    """Resolve opaque model refs through an operator-owned model catalog."""

    __default_model: str
    __models: dict[str, LlmModelRoute]
    __profiles: dict[str, LlmProfile]
    __providers: dict[LlmProviderApi, ILLMProvider]

    def __init__(
        self,
        config: LlmConfig,
        providers: tuple[ILLMProvider, ...],
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
        """Return the exact selected route capability without reconstruction."""
        return self._resolve_target(selection).route.capability

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Resolve one catalog route and delegate through its provider SDK."""
        target = self._resolve_target(request.model_selection)
        provider = self._provider_for(target)
        return await provider.complete(target, request)

    @override
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Resolve one catalog route and stream normalized provider events."""
        return self._stream(request)

    async def _stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        try:
            target = self._resolve_target(request.model_selection)
        except LlmModelSelectionError as error:
            model_ref = self._requested_model_ref(request.model_selection)
            metadata = {"model_ref": model_ref}
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
        try:
            if not target.profile.stream_enabled:
                raise LlmStreamingDisabledError
            provider = self._provider_for(target)
            async for event in provider.stream(target, request):
                yield event
        except AbstractLlmError as error:
            yield error_event(error, target)
            yield done_event(target, None, None)

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
