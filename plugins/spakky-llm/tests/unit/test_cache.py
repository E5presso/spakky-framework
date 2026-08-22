"""Tests for explicit exact and semantic LLM response-cache contracts."""

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import cast

import pytest
from pydantic import SecretStr
from pydantic import ValidationError
from spakky.agent import (
    JsonSchemaConstraint,
    JsonObject,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
    ModelToolSpec,
    ModelUsage,
    SamplingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
    JsonValue,
)
from spakky.agent.content import DocumentPart, ImagePart, TextPart

from spakky.plugins.llm.cache import (
    LlmCachedResponse,
    LlmCacheKeyBuilder,
    LlmCacheMode,
    LlmCachePolicy,
    LlmCacheScope,
)
from spakky.plugins.llm.config import (
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
)
from spakky.plugins.llm.provider import LlmModelTarget
from spakky.plugins.llm.error import LlmCacheConfigurationError


def _target(*, model_ref: str = "assistant/default") -> LlmModelTarget:
    profile = LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        api_key=SecretStr("secret"),
    )
    return LlmModelTarget(
        model_ref=model_ref,
        profile_name="openai-prod",
        profile=profile,
        route=LlmModelRoute(
            profile="openai-prod",
            model="gpt-model",
            capability=ModelCapability(
                supports_tools=True,
                supports_structured_output=True,
            ),
        ),
    )


def _request(
    *,
    tool_description: str = "Search records",
    schema_type: str = "string",
) -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "private prompt"),),
        tool_calling=ToolCallingSpec(
            tools=(
                ModelToolSpec(
                    name="search",
                    description=tool_description,
                    parameters=JsonSchemaConstraint(
                        schema={
                            "type": "object",
                            "properties": {"query": {"type": schema_type}},
                        }
                    ),
                ),
            )
        ),
        structured_output=StructuredOutputSpec(
            constraint=JsonSchemaConstraint(
                schema={
                    "type": "object",
                    "properties": {"answer": {"type": schema_type}},
                }
            )
        ),
        sampling=SamplingOptions(temperature=0.2, top_p=0.9, max_tokens=100),
        metadata={"cache_key": "caller-cannot-override", "api_key": "secret"},
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: LlmCachedResponse(ModelResponse(content=cast(str, 123))),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", structured_output=cast(JsonValue, object()))
        ),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", structured_output=float("inf"))
        ),
        lambda: LlmCachedResponse(
            ModelResponse(
                content="x",
                tool_calls=cast(Sequence[ModelToolCall], "bad"),
            )
        ),
        lambda: LlmCachedResponse(
            ModelResponse(
                content="x",
                tool_calls=cast(Sequence[ModelToolCall], (object(),)),
            )
        ),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", tool_calls=(ModelToolCall(" ", {}),))
        ),
        lambda: LlmCachedResponse(
            ModelResponse(
                content="x",
                tool_calls=(ModelToolCall("tool", cast(JsonObject, [])),),
            )
        ),
        lambda: LlmCachedResponse(
            ModelResponse(
                content="x",
                tool_calls=(ModelToolCall("tool", {}, metadata=cast(JsonObject, [])),),
            )
        ),
        lambda: LlmCachedResponse(
            ModelResponse(
                content="x",
                tool_calls=(ModelToolCall("tool", {}, call_id=" "),),
            )
        ),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", usage=cast(ModelUsage, object()))
        ),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", usage=ModelUsage(input_tokens=-1))
        ),
        lambda: LlmCachedResponse(
            ModelResponse(
                content="x",
                usage=ModelUsage(input_tokens=cast(int, True)),
            )
        ),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", metadata=cast(JsonObject, []))
        ),
        lambda: LlmCachedResponse(
            ModelResponse(content="x", metadata=cast(JsonObject, {1: "bad"}))
        ),
    ],
)
def test_cached_response_rejects_malformed_runtime_shape(
    factory: Callable[[], LlmCachedResponse],
) -> None:
    """Every cached response field is validated before it becomes a receipt."""
    with pytest.raises(LlmCacheConfigurationError):
        factory()


def test_cached_response_rejects_recursive_json() -> None:
    """Recursive cache values normalize to the typed cache boundary error."""
    recursive: dict[str, JsonValue] = {}
    recursive["self"] = recursive

    with pytest.raises(LlmCacheConfigurationError):
        LlmCachedResponse(ModelResponse(content="x", structured_output=recursive))


def test_cached_response_snapshot_preserves_json_array_shape() -> None:
    """Cache receipts copy mutable arrays without changing list/tuple semantics."""
    response = ModelResponse(
        content="x",
        structured_output={"list": [1], "tuple": (2,)},
        metadata={"list": [3]},
    )

    cached = LlmCachedResponse(response)
    cast(list[int], cast(dict[str, JsonValue], response.structured_output)["list"])[
        0
    ] = 9

    assert cached.response.structured_output == {
        "list": [1],
        "tuple": (2,),
    }
    assert cached.response.metadata == {"list": [3]}


def test_cache_json_snapshots_validate_keys_and_finite_numbers() -> None:
    """Canonical keys reject invalid JSON while response snapshots retain finite floats."""
    with pytest.raises(LlmCacheConfigurationError):
        LlmCacheKeyBuilder._json_value(float("inf"))
    with pytest.raises(LlmCacheConfigurationError):
        LlmCacheKeyBuilder._json_value(cast(JsonValue, {1: "bad"}))

    cached = LlmCachedResponse(
        ModelResponse(content="x", structured_output={"score": 1.5})
    )

    assert cached.response.structured_output == {"score": 1.5}


def test_exact_cache_key_expect_tenant_tool_schema_and_safety_sensitivity() -> None:
    """Every trusted semantic boundary changes the exact SHA-256 key."""
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    target = _target()
    base = LlmCacheKeyBuilder.build(
        policy,
        LlmCacheScope("tenant-a", "redaction-v1"),
        target,
        _request(),
    )
    other_tenant = LlmCacheKeyBuilder.build(
        policy,
        LlmCacheScope("tenant-b", "redaction-v1"),
        target,
        _request(),
    )
    other_safety = LlmCacheKeyBuilder.build(
        policy,
        LlmCacheScope("tenant-a", "redaction-v2"),
        target,
        _request(),
    )
    other_tool = LlmCacheKeyBuilder.build(
        policy,
        LlmCacheScope("tenant-a", "redaction-v1"),
        target,
        _request(tool_description="Search newer records"),
    )
    other_schema = LlmCacheKeyBuilder.build(
        policy,
        LlmCacheScope("tenant-a", "redaction-v1"),
        target,
        _request(schema_type="integer"),
    )

    assert (
        len(
            {
                base.key.digest,
                other_tenant.key.digest,
                other_safety.key.digest,
                other_tool.key.digest,
                other_schema.key.digest,
            }
        )
        == 5
    )


def test_exact_cache_key_expect_route_sampling_and_content_sensitivity() -> None:
    """Logical/physical route, sampling, and body fingerprints cannot collide."""
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    scope = LlmCacheScope("tenant-a", "redaction-v1")
    request = _request()
    base = LlmCacheKeyBuilder.build(policy, scope, _target(), request)
    other_route = LlmCacheKeyBuilder.build(
        policy,
        scope,
        _target(model_ref="assistant/fallback"),
        request,
    )
    other_sampling = LlmCacheKeyBuilder.build(
        policy,
        scope,
        _target(),
        replace(request, sampling=SamplingOptions(temperature=0.8)),
    )
    other_body = LlmCacheKeyBuilder.build(
        policy,
        scope,
        _target(),
        replace(
            request,
            messages=(ModelMessage(ModelMessageRole.USER, "different prompt"),),
        ),
    )

    assert (
        len(
            {
                base.key.digest,
                other_route.key.digest,
                other_sampling.key.digest,
                other_body.key.digest,
            }
        )
        == 4
    )


def test_exact_cache_key_binds_route_capability_template_and_connection() -> None:
    """Response-affecting operator route/profile changes invalidate persistent hits."""
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    scope = LlmCacheScope("tenant-a", "redaction-v1")
    request = _request()
    target = _target()
    changed_capability = replace(
        target,
        route=target.route.model_copy(
            update={
                "capability": ModelCapability(supports_reasoning=True),
            }
        ),
    )
    changed_template = replace(
        target,
        route=target.route.model_copy(
            update={"chat_template_kwargs": {"enable_thinking": True}}
        ),
    )
    changed_connection = replace(
        target,
        profile=target.profile.model_copy(
            update={"base_url": "https://other.example.test/v1"}
        ),
    )

    digests = {
        LlmCacheKeyBuilder.build(policy, scope, candidate, request).key.digest
        for candidate in (
            target,
            changed_capability,
            changed_template,
            changed_connection,
        )
    }

    assert len(digests) == 4


def test_cache_key_expect_arbitrary_request_metadata_cannot_override_key() -> None:
    """Caller metadata is excluded while trusted scope remains authoritative."""
    policy = LlmCachePolicy(mode=LlmCacheMode.EXACT)
    scope = LlmCacheScope("tenant-a", "redaction-v1")
    request = _request()
    changed_metadata = replace(
        request,
        metadata={"cache_key": "attacker", "tenant_scope": "tenant-b"},
    )

    first = LlmCacheKeyBuilder.build(policy, scope, _target(), request)
    second = LlmCacheKeyBuilder.build(policy, scope, _target(), changed_metadata)

    assert first.key.digest == second.key.digest
    assert first.key.tenant_scope == "tenant-a"


def test_cache_key_expect_multimodal_bytes_and_uri_are_hashed() -> None:
    """Multipart bodies influence keys without entering privacy-safe key fields."""
    request = ModelRequest(
        messages=(
            ModelMessage.user(
                (
                    TextPart("describe"),
                    ImagePart.from_bytes(b"image-bytes", media_type="image/png"),
                )
            ),
        )
    )
    query = LlmCacheKeyBuilder.build(
        LlmCachePolicy(mode=LlmCacheMode.EXACT),
        LlmCacheScope("tenant-a", "redaction-v1"),
        _target(),
        request,
    )

    assert len(query.key.digest) == 64
    assert "image-bytes" not in repr(query.key)
    assert query.semantic_input == ()


def test_semantic_cache_mode_expect_distinct_query_mode_and_semantic_input() -> None:
    """Semantic mode remains explicit and receives content rather than exact emulation."""
    query = LlmCacheKeyBuilder.build(
        LlmCachePolicy(mode=LlmCacheMode.SEMANTIC),
        LlmCacheScope("tenant-a", "redaction-v1"),
        _target(),
        _request(),
    )

    assert query.mode is LlmCacheMode.SEMANTIC
    assert query.semantic_input == ("user:private prompt",)


def test_cache_policy_and_scope_expect_normalized_nonblank_partitions() -> None:
    """Cache namespace trims while blank namespaces and trusted scopes fail closed."""
    assert LlmCachePolicy(namespace=" tenant-cache ").namespace == "tenant-cache"
    with pytest.raises(ValidationError):
        LlmCachePolicy(namespace=" ")
    with pytest.raises(LlmCacheConfigurationError):
        LlmCacheScope("", "safety")
    with pytest.raises(LlmCacheConfigurationError):
        LlmCacheScope("tenant", " ")


def test_document_cache_key_expect_filename_and_source_provenance_bound() -> None:
    """Document filename, bytes, and provenance participate only as fingerprints."""
    request = ModelRequest(
        messages=(
            ModelMessage.user(
                (
                    DocumentPart.from_bytes(
                        b"pdf-body",
                        media_type="application/pdf",
                        filename="report.pdf",
                        source="upload-1",
                    ),
                )
            ),
        )
    )

    query = LlmCacheKeyBuilder.build(
        LlmCachePolicy(mode=LlmCacheMode.EXACT),
        LlmCacheScope("tenant", "safety"),
        _target(),
        request,
    )

    assert len(query.key.digest) == 64
    assert "pdf-body" not in repr(query.key)


def test_cache_canonicalizer_expect_non_json_runtime_value_rejected() -> None:
    """A type-corrupted value cannot enter a deterministic cache fingerprint."""
    malformed = cast(JsonValue, object())  # external corruption boundary probe

    with pytest.raises(LlmCacheConfigurationError):
        LlmCacheKeyBuilder._json_value(malformed)


def test_cached_response_validates_type_and_snapshots_original_alias() -> None:
    """A cache receipt cannot retain the caller's mutable response metadata alias."""
    metadata: dict[str, JsonValue] = {"nested": {"value": 1}}
    cached = LlmCachedResponse(ModelResponse(content="ok", metadata=metadata))
    cast(dict[str, JsonValue], metadata["nested"])["value"] = 2

    assert cached.response.metadata == {"nested": {"value": 1}}
    with pytest.raises(LlmCacheConfigurationError):
        LlmCachedResponse(cast(ModelResponse, object()))
