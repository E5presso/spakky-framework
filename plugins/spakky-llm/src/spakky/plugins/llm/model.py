"""Allowlisted multi-provider implementation of the agent model port."""

from collections.abc import AsyncIterator
from typing import override

from spakky.agent import (
    IAgentModel,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
)
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.config import LlmConfig, LlmProfile, LlmProviderApi
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
    """Route each model request to an operator-allowlisted native SDK profile."""

    __config: LlmConfig
    __providers: dict[LlmProviderApi, ILLMProvider]

    def __init__(
        self,
        config: LlmConfig,
        providers: tuple[ILLMProvider, ...],
    ) -> None:
        self.__config = config
        self.__providers = self._provider_registry(providers)
        configured_apis = {profile.api for profile in config.profiles.values()}
        if not configured_apis.issubset(self.__providers):
            raise LlmConfigurationError

    @property
    @override
    def capability(self) -> ModelCapability:
        """Return the capability of the configured default profile."""
        return self._capability(self._default_target().profile)

    @override
    def capability_for(
        self,
        selection: ModelSelection | None = None,
    ) -> ModelCapability:
        """Return capability for the profile selected by one run."""
        return self._capability(self._resolve_target(selection).profile)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Resolve one profile and delegate through its official provider SDK."""
        target = self._resolve_target(request.model_selection)
        provider = self._provider_for(target)
        return await provider.complete(target, request)

    @override
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        """Resolve one profile and stream normalized provider events."""
        return self._stream(request)

    async def _stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        target = self._default_target()
        try:
            target = self._resolve_target(request.model_selection)
            if not target.profile.stream_enabled:
                raise LlmStreamingDisabledError
            provider = self._provider_for(target)
            async for event in provider.stream(target, request):
                yield event
        except AbstractLlmError as error:
            yield error_event(error, target)
            yield done_event(target, None, None)

    def _default_target(self) -> LlmModelTarget:
        profile = self.__config.profiles[self.__config.default_profile]
        return LlmModelTarget(
            profile_name=self.__config.default_profile,
            profile=profile,
            model=profile.model,
        )

    def _resolve_target(
        self,
        selection: ModelSelection | None,
    ) -> LlmModelTarget:
        if selection is None:
            return self._default_target()
        profile_name = self._profile_name(selection)
        profile = self.__config.profiles.get(profile_name)
        if profile is None:
            raise LlmModelSelectionError
        if selection.provider is not None and selection.provider != profile.provider:
            raise LlmModelSelectionError
        return LlmModelTarget(
            profile_name=profile_name,
            profile=profile,
            model=selection.model or profile.model,
        )

    def _profile_name(self, selection: ModelSelection) -> str:
        if selection.profile is not None:
            return selection.profile
        if selection.provider is None:
            return self.__config.default_profile
        matches = tuple(
            name
            for name, profile in self.__config.profiles.items()
            if profile.provider == selection.provider
        )
        if len(matches) != 1:
            raise LlmModelSelectionError
        return matches[0]

    def _provider_for(self, target: LlmModelTarget) -> ILLMProvider:
        provider = self.__providers.get(target.profile.api)
        if provider is None:
            raise LlmProviderUnavailableError
        return provider

    def _provider_registry(
        self,
        providers: tuple[ILLMProvider, ...],
    ) -> dict[LlmProviderApi, ILLMProvider]:
        registry: dict[LlmProviderApi, ILLMProvider] = {}
        for provider in providers:
            if provider.api in registry:
                raise LlmConfigurationError
            registry[provider.api] = provider
        return registry

    def _capability(self, profile: LlmProfile) -> ModelCapability:
        return ModelCapability(
            supports_reasoning=profile.supports_reasoning,
            context_window_tokens=profile.context_window_tokens,
            supports_token_counting=profile.supports_token_counting,
        )
