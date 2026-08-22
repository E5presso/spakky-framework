"""Explicit exact and semantic response-cache contracts for LLM completion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import isfinite
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError
from spakky.agent import (
    JsonObject,
    JsonValue,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    ModelUsage,
)
from spakky.agent.content import (
    AudioPart,
    DocumentPart,
    ImagePart,
    TextPart,
    VideoPart,
    model_content_parts,
)

from spakky.plugins.llm.error import LlmCacheConfigurationError

if TYPE_CHECKING:
    from spakky.plugins.llm.provider import LlmModelTarget


class LlmCacheMode(StrEnum):
    """Replacement mode selected by one logical model route."""

    DISABLED = "disabled"
    EXACT = "exact"
    SEMANTIC = "semantic"


class LlmCachePolicy(BaseModel):
    """Route-owned response-cache policy, disabled unless explicitly selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: LlmCacheMode = LlmCacheMode.DISABLED
    ttl_seconds: float = Field(default=300.0, gt=0)
    namespace: str = Field(default="spakky-llm:v1", min_length=1, strict=True)

    @field_validator("namespace")
    @classmethod
    def _normalize_namespace(cls, value: str) -> str:
        normalized = value.strip()
        if normalized == "":
            raise PydanticCustomError(
                "llm_cache_namespace",
                "LLM cache namespace cannot be blank",
            )
        return normalized


@dataclass(frozen=True, slots=True)
class LlmCacheScope:
    """Trusted cache partition resolved outside arbitrary request metadata."""

    tenant_scope: str
    safety_scope: str

    def __post_init__(self) -> None:
        if self.tenant_scope.strip() == "" or self.safety_scope.strip() == "":
            raise LlmCacheConfigurationError


@dataclass(frozen=True, slots=True)
class LlmCacheKey:
    """Privacy-safe exact key carrying only route and partition evidence."""

    digest: str
    namespace: str
    tenant_scope: str
    safety_scope: str
    model_ref: str
    profile_name: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class LlmCacheLookup:
    """Cache lookup with a distinct semantic input for semantic backends."""

    mode: LlmCacheMode
    key: LlmCacheKey
    semantic_input: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LlmCachedResponse:
    """Complete tool-free response stored by a replaceable cache backend."""

    response: ModelResponse

    def __post_init__(self) -> None:
        if not isinstance(self.response, ModelResponse):
            raise LlmCacheConfigurationError
        object.__setattr__(self, "response", _snapshot_response(self.response))


class ILLMResponseCache(ABC):
    """Replaceable cache port; no in-memory production implementation is implicit."""

    @property
    @abstractmethod
    def mode(self) -> LlmCacheMode:
        """Return the one lookup mode implemented by this backend."""
        ...

    @abstractmethod
    async def lookup(self, query: LlmCacheLookup) -> LlmCachedResponse | None:
        """Return an exact or semantic hit according to the backend mode."""
        ...

    @abstractmethod
    async def store(
        self,
        query: LlmCacheLookup,
        response: LlmCachedResponse,
        *,
        ttl_seconds: float,
    ) -> None:
        """Store one complete tool-free response with the configured TTL."""
        ...


class ILLMCacheScopeResolver(ABC):
    """Resolve trusted tenant and safety partitions independently of metadata keys."""

    @abstractmethod
    def resolve(self, request: ModelRequest) -> LlmCacheScope:
        """Return the authoritative cache partition for one request."""
        ...


class LlmCacheKeyBuilder:
    """Build canonical SHA-256 request fingerprints without exposing bodies."""

    @classmethod
    def build(
        cls,
        policy: LlmCachePolicy,
        scope: LlmCacheScope,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> LlmCacheLookup:
        """Bind route, guarded content, tools, schema, sampling, and safety scope."""
        assembled = request.assemble_messages()
        messages: list[JsonValue] = []
        semantic_input: list[str] = []
        for message in assembled:
            content_fingerprint, semantic_parts = cls._content(message.content)
            semantic_input.extend(
                f"{message.role.value}:{part}" for part in semantic_parts
            )
            messages.append(
                {
                    "role": message.role.value,
                    "content": content_fingerprint,
                    "metadata_sha256": cls._hash_json(message.metadata),
                }
            )
        payload: dict[str, JsonValue] = {
            "namespace": policy.namespace,
            "tenant_scope": scope.tenant_scope,
            "safety_scope": scope.safety_scope,
            "route": {
                "model_ref": target.model_ref,
                "profile": target.profile_name,
                "provider": target.profile.provider,
                "api": target.profile.api.value,
                "model": target.model,
                "capability": {
                    "supports_reasoning": target.route.capability.supports_reasoning,
                    "context_window_tokens": (
                        target.route.capability.context_window_tokens
                    ),
                    "supports_token_counting": (
                        target.route.capability.supports_token_counting
                    ),
                    "input_modalities": tuple(
                        sorted(
                            modality.value
                            for modality in target.route.capability.input_modalities
                        )
                    ),
                    "output_modalities": tuple(
                        sorted(
                            modality.value
                            for modality in target.route.capability.output_modalities
                        )
                    ),
                    "supports_tools": target.route.capability.supports_tools,
                    "supports_structured_output": (
                        target.route.capability.supports_structured_output
                    ),
                },
                "chat_template_kwargs": cls._json_value(
                    target.route.chat_template_kwargs
                ),
                "connection_sha256": cls._hash_json(
                    {
                        "provider": target.profile.provider,
                        "api": target.profile.api.value,
                        "base_url": target.profile.base_url,
                        "headers": target.profile.headers,
                        "openai_dialect": target.profile.openai_dialect.value,
                        "google_project": target.profile.google_project,
                        "google_location": target.profile.google_location,
                    }
                ),
            },
            "messages": messages,
            "context_manifest_ref": (
                request.context_manifest.id
                if request.context_manifest is not None
                else None
            ),
            "context_digest": (
                request.context_digest.digest
                if request.context_digest is not None
                else None
            ),
            "tool_calling": cls._tool_calling(request),
            "structured_output": cls._structured_output(request),
            "sampling": {
                "temperature": request.sampling.temperature,
                "top_p": request.sampling.top_p,
                "max_tokens": request.sampling.max_tokens,
            },
        }
        encoded = dumps(
            cls._json_value(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        key = LlmCacheKey(
            digest=sha256(encoded.encode("utf-8")).hexdigest(),
            namespace=policy.namespace,
            tenant_scope=scope.tenant_scope,
            safety_scope=scope.safety_scope,
            model_ref=target.model_ref,
            profile_name=target.profile_name,
            provider=target.profile.provider,
            model=target.model,
        )
        return LlmCacheLookup(
            mode=policy.mode,
            key=key,
            semantic_input=(
                tuple(semantic_input) if policy.mode is LlmCacheMode.SEMANTIC else ()
            ),
        )

    @classmethod
    def _tool_calling(cls, request: ModelRequest) -> JsonValue:
        tool_calling = request.tool_calling
        if tool_calling is None:
            return None
        tools: list[JsonValue] = []
        for tool in tool_calling.tools:
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "strict": tool.parameters.strict,
                    "schema": cls._json_value(tool.parameters.schema),
                    "metadata_sha256": cls._hash_json(tool.metadata),
                }
            )
        return {"choice": tool_calling.choice.value, "tools": tools}

    @classmethod
    def _structured_output(cls, request: ModelRequest) -> JsonValue:
        structured = request.structured_output
        if structured is None:
            return None
        return {
            "strict": structured.constraint.strict,
            "schema": cls._json_value(structured.constraint.schema),
            "output_type_name": structured.output_type_name,
        }

    @classmethod
    def _content(
        cls,
        content: str
        | Sequence[TextPart | ImagePart | AudioPart | VideoPart | DocumentPart],
    ) -> tuple[JsonValue, tuple[str, ...]]:
        if isinstance(content, str):
            return (
                {"type": "text", "sha256": cls._hash_text(content)},
                (content,),
            )
        fingerprints: list[JsonValue] = []
        semantic_parts: list[str] = []
        for part in model_content_parts(content):
            if isinstance(part, TextPart):
                fingerprints.append(
                    {"type": "text", "sha256": cls._hash_text(part.text)}
                )
                semantic_parts.append(part.text)
                continue
            source_kind = "uri" if part.uri is not None else "inline"
            source_value = (
                part.uri.encode("utf-8") if part.uri is not None else (part.data or b"")
            )
            digest = sha256(source_value).hexdigest()
            fingerprint: dict[str, JsonValue] = {
                "type": type(part).__name__,
                "media_type": part.media_type,
                "source_kind": source_kind,
                "source_sha256": digest,
                "content_digest": part.content_digest,
                "source_ref_sha256": (
                    cls._hash_text(part.source) if part.source is not None else None
                ),
            }
            if isinstance(part, DocumentPart):
                fingerprint["filename"] = part.filename
            fingerprints.append(fingerprint)
            semantic_parts.append(f"{part.media_type}:{part.content_digest or digest}")
        return tuple(fingerprints), tuple(semantic_parts)

    @classmethod
    def _hash_json(cls, value: JsonValue) -> str:
        encoded = dumps(
            cls._json_value(value),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_text(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _json_value(cls, value: JsonValue) -> JsonValue:
        if value is None or isinstance(value, str | bool | int):
            return value
        if isinstance(value, float):
            if not isfinite(value):
                raise LlmCacheConfigurationError
            return value
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise LlmCacheConfigurationError
            return {
                key: cls._json_value(item)
                for key, item in sorted(value.items(), key=lambda entry: entry[0])
            }
        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
            return tuple(cls._json_value(item) for item in value)
        raise LlmCacheConfigurationError


def _snapshot_response(response: ModelResponse) -> ModelResponse:
    try:
        if not isinstance(response.content, str):
            raise LlmCacheConfigurationError
        structured_output = _snapshot_response_json(response.structured_output)
        if not isinstance(response.tool_calls, Sequence) or isinstance(
            response.tool_calls,
            str | bytes | bytearray,
        ):
            raise LlmCacheConfigurationError
        tool_calls = tuple(_snapshot_tool_call(call) for call in response.tool_calls)
        usage = _snapshot_usage(response.usage)
        metadata = _snapshot_json_object(response.metadata)
        return ModelResponse(
            content=response.content,
            structured_output=structured_output,
            tool_calls=tool_calls,
            usage=usage,
            metadata=metadata,
        )
    except RecursionError as error:
        raise LlmCacheConfigurationError from error


def _snapshot_tool_call(call: object) -> ModelToolCall:
    if (
        not isinstance(call, ModelToolCall)
        or not isinstance(call.name, str)
        or not call.name.strip()
        or not isinstance(call.arguments, Mapping)
        or not isinstance(call.metadata, Mapping)
        or (
            call.call_id is not None
            and (not isinstance(call.call_id, str) or not call.call_id.strip())
        )
    ):
        raise LlmCacheConfigurationError
    return ModelToolCall(
        name=call.name,
        arguments=_snapshot_json_object(call.arguments),
        call_id=call.call_id,
        metadata=_snapshot_json_object(call.metadata),
    )


def _snapshot_usage(usage: object) -> ModelUsage:
    if not isinstance(usage, ModelUsage):
        raise LlmCacheConfigurationError
    values = (
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
        usage.cached_input_tokens,
        usage.cache_write_input_tokens,
        usage.cache_write_5m_input_tokens,
        usage.cache_write_1h_input_tokens,
    )
    if any(
        value is not None
        and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
        for value in values
    ):
        raise LlmCacheConfigurationError
    return deepcopy(usage)


def _snapshot_json_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        raise LlmCacheConfigurationError
    return cast(JsonObject, _snapshot_response_json(value))


def _snapshot_response_json(value: object) -> JsonValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise LlmCacheConfigurationError
        return value
    if isinstance(value, Mapping):
        snapshot: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise LlmCacheConfigurationError
            snapshot[key] = _snapshot_response_json(item)
        return snapshot
    if isinstance(value, Sequence) and not isinstance(
        value,
        str | bytes | bytearray,
    ):
        items = [_snapshot_response_json(item) for item in value]
        return tuple(items) if isinstance(value, tuple) else items
    raise LlmCacheConfigurationError
