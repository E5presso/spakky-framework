"""Tests for agent model interface contracts."""

from collections.abc import AsyncIterator

import pytest

from spakky.agent import (
    ContextDigest,
    ContextExposurePolicy,
    ContextFreshness,
    ContextManifest,
    ContextManifestEntry,
    ContextPack,
    ContextPackRole,
    ContextSensitivity,
    ContextTokenBudget,
    EvidenceExposurePolicy,
    IAgentModel,
    JsonSchemaConstraint,
    MaskingPolicy,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelToolSpec,
    PII,
    RedactionPolicy,
    SamplingOptions,
    SecretField,
    SensitiveField,
    SensitiveFieldDescriptor,
    StreamingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)


class FakeAgentModel(IAgentModel):
    """Test double for the abstract model port."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=f"complete:{len(request.messages)}",
            structured_output={"ok": True},
            tool_calls=(
                ModelToolCall(name="search_docs", arguments={"query": "agent"}),
            ),
        )

    async def _events(self) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="hi",
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(name="search_docs", arguments={"query": "agent"}),
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
            structured_output={"ok": True},
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=ModelError(
                code="rate_limited", message="retry later", retryable=True
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        return self._events()


def test_model_request_expect_provider_neutral_structured_output_contract() -> None:
    """ModelRequest가 JSON schema 기반 structured output spec을 보존한다."""
    constraint = JsonSchemaConstraint(schema={"type": "object"})
    tool = ModelToolSpec(
        name="search_docs",
        description="Search documentation",
        parameters=JsonSchemaConstraint(schema={"type": "object"}),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
        structured_output=StructuredOutputSpec(constraint=constraint),
        tool_calling=ToolCallingSpec(tools=(tool,), choice=ModelToolChoice.REQUIRED),
        sampling=SamplingOptions(temperature=0.2, max_tokens=64),
        streaming=StreamingOptions(include_usage=True, include_progress=False),
    )

    assert request.messages[0].role == ModelMessageRole.USER
    assert request.structured_output is not None
    assert request.structured_output.constraint is constraint
    assert request.tool_calling is not None
    assert request.tool_calling.tools == (tool,)
    assert request.tool_calling.choice == ModelToolChoice.REQUIRED
    assert request.sampling.temperature == 0.2
    assert request.sampling.max_tokens == 64
    assert request.streaming.include_usage is True
    assert request.streaming.include_progress is False


def test_model_request_expect_assembles_typed_context_packs_as_messages() -> None:
    """ModelRequest는 raw 문자열 결합 대신 ContextPack 기반 메시지를 조립한다."""
    pack = ContextPack(
        id="pack-1",
        content="ticket context",
        source="issue:#233",
        role=ContextPackRole.EVIDENCE,
        freshness=ContextFreshness.CURRENT,
        relevance=0.92,
        token_budget=ContextTokenBudget(max_tokens=512, estimated_tokens=128),
        sensitivity=ContextSensitivity.CONFIDENTIAL,
        metadata={"origin": "github"},
    )
    manifest = ContextManifest(
        id="manifest-1",
        entries=(
            ContextManifestEntry(
                pack_id="pack-1",
                source="issue:#233",
                role=ContextPackRole.EVIDENCE,
                origin_ref="github:issue:233",
                evidence_ref="evidence-1",
            ),
        ),
        evidence_refs=("evidence-1",),
    )
    digest = ContextDigest(
        id="digest-1",
        context_identity="agent-run:state-1:model-call-1",
        source_manifest_ref="manifest-1",
        digest="sha256:abc123",
        derived_from_pack_ids=("pack-1",),
        compression_evidence_ref="evidence-2",
        algorithm="summary-v1",
    )

    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "summarize"),),
        context=(pack,),
        context_manifest=manifest,
        context_digest=digest,
    )

    assembled = request.assemble_messages()

    assert assembled == (
        ModelMessage(ModelMessageRole.USER, "summarize"),
        ModelMessage(
            role=ModelMessageRole.EVIDENCE,
            content="ticket context",
            metadata={
                "context_pack_id": "pack-1",
                "source": "issue:#233",
                "role": "evidence",
                "freshness": "current",
                "relevance": 0.92,
                "token_budget": {
                    "max_tokens": 512,
                    "estimated_tokens": 128,
                    "reserved_output_tokens": None,
                },
                "sensitivity": "confidential",
                "metadata": {"origin": "github"},
            },
        ),
    )
    assert request.context_manifest is manifest
    assert request.context_digest is digest


def test_model_request_expect_guards_sensitive_context_before_assembly() -> None:
    """secret/PII context는 model message 조립 전에 deterministic guard를 지난다."""
    secret_pack = ContextPack(
        id="pack-secret",
        content="sk-live-1234",
        source="vault:secret",
        role=ContextPackRole.EVIDENCE,
        sensitive_fields=(SensitiveFieldDescriptor((), SecretField()),),
    )
    email_pack = ContextPack(
        id="pack-email",
        content="owner@example.com",
        source="profile:1",
        role=ContextPackRole.EVIDENCE,
        sensitive_fields=(
            SensitiveFieldDescriptor(
                (),
                SensitiveField(PII.EMAIL, masking=MaskingPolicy.HASH),
            ),
        ),
    )
    request = ModelRequest(
        messages=(ModelMessage(ModelMessageRole.USER, "inspect"),),
        context=(secret_pack, email_pack),
    )

    assembled = request.assemble_messages()
    metadata_visible = request.assemble_messages(
        ContextExposurePolicy(include_sensitive_context_metadata=True)
    )

    assert assembled[1].content == "[SECRET]"
    assert assembled[2].content.startswith("[HASHED:email:")
    assert "owner@example.com" not in assembled[2].content
    assert "sensitive_fields" not in assembled[1].metadata
    assert metadata_visible[1].metadata == {
        "context_pack_id": "pack-secret",
        "source": "vault:secret",
        "role": "evidence",
        "freshness": "unknown",
        "relevance": None,
        "token_budget": {
            "max_tokens": None,
            "estimated_tokens": None,
            "reserved_output_tokens": None,
        },
        "sensitivity": "internal",
        "metadata": {},
        "sensitive_fields": (
            {
                "path": [],
                "field": {
                    "kind": "secret",
                    "sensitivity": "secret",
                    "redaction": "reference_only",
                },
            },
        ),
    }


def test_context_pack_expect_redacted_and_dropped_content_become_safe_text() -> None:
    """ContextPack 자체가 redacted/drop 상태를 safe text로 변환한다."""
    redacted_pack = ContextPack(
        id="pack-redacted",
        content="raw",
        source="guard",
        role=ContextPackRole.EVIDENCE,
        sensitivity=ContextSensitivity.REDACTED,
    )
    dropped_pack = ContextPack(
        id="pack-dropped",
        content="raw",
        source="guard",
        role=ContextPackRole.EVIDENCE,
        sensitive_fields=(
            SensitiveFieldDescriptor(
                (),
                SensitiveField(PII.IDENTIFIER, redaction=RedactionPolicy.DROP),
            ),
        ),
    )

    assert redacted_pack.guarded_content() == "[REDACTED]"
    assert dropped_pack.guarded_content() == "[REDACTED]"


def test_model_output_and_stream_expect_apply_path_bound_guard() -> None:
    """model output/stream payload도 path-bound guard를 재사용한다."""
    email_field = SensitiveFieldDescriptor(("email",), SensitiveField(PII.EMAIL))
    token_field = SensitiveFieldDescriptor((), SecretField())
    response = ModelResponse(
        content="final raw",
        structured_output={"email": "owner@example.com", "status": "ok"},
        tool_calls=(ModelToolCall(name="notify", arguments={"email": "x@y.z"}),),
    )
    stream_event = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="sk-live-1234",
        structured_output={"email": "owner@example.com"},
    )

    guarded_response = response.guarded((email_field,))
    guarded_stream = stream_event.guarded(
        (token_field, email_field),
        EvidenceExposurePolicy(),
    )

    assert guarded_response.structured_output == {
        "email": "[REDACTED]",
        "status": "ok",
    }
    assert guarded_response.content == "final raw"
    assert guarded_stream.token_delta == "[SECRET]"
    assert guarded_stream.structured_output == {"email": "[REDACTED]"}


def test_model_output_and_stream_expect_handle_root_and_empty_guards() -> None:
    """guard helper는 root descriptors, empty stream fields, tool calls를 처리한다."""
    root_secret = SensitiveFieldDescriptor((), SecretField())
    call = ModelToolCall(name="submit", arguments={"secret": "raw"}).guarded(
        (root_secret,)
    )
    response = ModelResponse(
        content="owner@example.com",
        structured_output={"status": "ok"},
    ).guarded((SensitiveFieldDescriptor(("content",), SensitiveField(PII.EMAIL)),))
    dropped_response = ModelResponse(
        content="owner@example.com",
    ).guarded(
        (
            SensitiveFieldDescriptor(
                ("content",),
                SensitiveField(PII.EMAIL, redaction=RedactionPolicy.DROP),
            ),
        )
    )
    unstructured_response = ModelResponse(content="ok").guarded(
        (SensitiveFieldDescriptor(("email",), SensitiveField(PII.EMAIL)),)
    )
    event = ModelStreamEvent(
        kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        tool_call=ModelToolCall(name="submit", arguments={"secret": "raw"}),
    ).guarded((SensitiveFieldDescriptor(("secret",), SecretField()),))
    token_without_matching_descriptor = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="plain",
    ).guarded((SensitiveFieldDescriptor(("email",), SensitiveField(PII.EMAIL)),))
    token_only_descriptor = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="raw",
    ).guarded((SensitiveFieldDescriptor(("token_delta",), SecretField()),))
    dropped_token = ModelStreamEvent(
        kind=ModelStreamEventKind.TOKEN_DELTA,
        token_delta="raw",
    ).guarded(
        (
            SensitiveFieldDescriptor(
                ("token_delta",),
                SensitiveField(PII.IDENTIFIER, redaction=RedactionPolicy.DROP),
            ),
        )
    )

    assert call.arguments == {}
    assert response.content == "[REDACTED]"
    assert response.structured_output == {"status": "ok"}
    assert dropped_response.content == "[REDACTED]"
    assert unstructured_response.structured_output is None
    assert event.token_delta is None
    assert event.structured_output is None
    assert event.tool_call == ModelToolCall(
        name="submit",
        arguments={"secret": "[SECRET]"},
    )
    assert token_without_matching_descriptor.token_delta == "plain"
    assert token_without_matching_descriptor.structured_output is None
    assert token_only_descriptor.token_delta == "[SECRET]"
    assert token_only_descriptor.structured_output is None
    assert dropped_token.token_delta == "[REDACTED]"


@pytest.mark.asyncio
async def test_agent_model_expect_complete_and_stream_are_typed_port_methods() -> None:
    """IAgentModel 구현체가 complete와 stream 계약을 제공한다."""
    model = FakeAgentModel()
    request = ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))

    response = await model.complete(request)
    events = [event async for event in model.stream(request)]

    assert response.content == "complete:1"
    assert response.structured_output == {"ok": True}
    assert response.tool_calls == (
        ModelToolCall(name="search_docs", arguments={"query": "agent"}),
    )
    assert events == [
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="hi",
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(name="search_docs", arguments={"query": "agent"}),
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
            structured_output={"ok": True},
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.ERROR,
            error=ModelError(
                code="rate_limited", message="retry later", retryable=True
            ),
        ),
        ModelStreamEvent(kind=ModelStreamEventKind.DONE),
    ]


def test_model_stream_event_kind_expect_issue_216_required_vocabulary() -> None:
    """Model stream event가 #216 수용 기준의 canonical event kind를 노출한다."""
    assert {kind.value for kind in ModelStreamEventKind} == {
        "token_delta",
        "tool_call_candidate",
        "structured_output",
        "progress",
        "error",
        "done",
    }
