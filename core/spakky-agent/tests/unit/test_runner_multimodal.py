"""Tests for multimodal content through the standard Agent runner path."""

from base64 import b64encode
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast, override

import pytest
import spakky.agent.runner as runner_module
from spakky.agent import content as content_module
from spakky.agent import (
    AgentEvidence,
    AgentEvidenceKind,
    AgentRunner,
    AgentYieldKind,
    Approval,
    Error,
    ImagePart,
    JsonObject,
    JsonValue,
    MediaSafetyLimits,
    ModelCapability,
    ModelMessage,
    ModelMessageRole,
    ModelModality,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    RunAgentInput,
    TextPart,
    Token,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.runner import RUNNER_CHECKPOINT_METADATA_KEY
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
)
from tests.unit.test_runner import (
    ProbeAgent,
    ScriptedRoundModel,
    StatelessProbeAgent,
    _approval_signal,
    _collect,
    _tool_event,
)


class MultimodalScriptedModel(ScriptedRoundModel):
    """Scripted model advertising text and image input support."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(
            input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
        )


class FallbackAwareReasoningModel(ScriptedRoundModel):
    """Routing adapter fixture whose actual attempt owns reasoning capability."""

    @override
    def validate_request(self, request: ModelRequest) -> None:
        return None


class ReorderedEvidenceRepository(FakeEvidenceRepository):
    """Replaceable repository returning evidence in reverse insertion order."""

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        return tuple(reversed(super().list_by_state(state_id)))


async def test_standard_runner_passes_ordered_attachments_to_first_model_step() -> None:
    """RunAgentInput turns text plus attachments into one portable user message."""
    image = ImagePart.from_bytes(
        b"image-body",
        media_type="image/png",
        source="upload:1",
    )
    model = MultimodalScriptedModel(
        ((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),)
    )

    items = await _collect(
        AgentRunner.for_agent_instance(StatelessProbeAgent(model)).run(
            RunAgentInput(
                state_id="multimodal-run",
                instruction="describe",
                attachments=(image,),
            )
        )
    )

    assert items[-1].kind is AgentYieldKind.FINAL
    user = next(
        message
        for message in model.requests[0].messages
        if message.role is ModelMessageRole.USER
    )
    assert user.content == (TextPart("describe"), image)


async def test_standard_runner_rejects_unsupported_modality_before_model_io() -> None:
    """A text-only fixed model never receives an image-bearing request."""
    model = ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),))

    items = await _collect(
        AgentRunner.for_agent_instance(StatelessProbeAgent(model)).run(
            RunAgentInput(
                state_id="unsupported-image",
                instruction="describe",
                attachments=(ImagePart.from_bytes(b"image", media_type="image/png"),),
            )
        )
    )

    assert isinstance(items[-1].payload, Error)
    assert items[-1].payload.code == "agent_model_execution_failed"
    assert model.requests == []


async def test_runner_trusts_reasoning_event_from_fallback_aware_model() -> None:
    """A capable fallback may expose reasoning even when the primary descriptor cannot."""
    model = FallbackAwareReasoningModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.REASONING_DELTA,
                    reasoning_delta="fallback reasoning",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )

    items = await _collect(
        AgentRunner.for_agent_instance(StatelessProbeAgent(model)).run(
            RunAgentInput(state_id="fallback-reasoning", instruction="answer")
        )
    )

    assert any(
        isinstance(item.payload, Token) and item.payload.text == "fallback reasoning"
        for item in items
    )


async def test_durable_multimodal_checkpoint_round_trips_before_resume() -> None:
    """Inline media and its safety limits survive an approval restart exactly."""
    state_id = "multimodal-resume"
    image = ImagePart.from_bytes(
        b"private-image-body",
        media_type="image/png",
        source="upload:1",
        content_digest="sha256:image",
    )
    remote = ImagePart.from_uri(
        "gs://bucket/image.png",
        media_type="image/png",
        limits=MediaSafetyLimits(
            allowed_uri_schemes=frozenset({"https", "gs"}),
        ),
    )
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    target = ProbeAgent(
        model,
        states,
        signals,
        FakeEvidenceRepository(),
    )
    runner = AgentRunner.for_agent_instance(target)

    paused = await _collect(
        runner.run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                attachments=(image, remote),
            )
        )
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    checkpoint = states.get(state_id).metadata[RUNNER_CHECKPOINT_METADATA_KEY]
    assert isinstance(checkpoint, Mapping)
    assert "private-image-body" not in repr(checkpoint)
    signals.append(_approval_signal(state_id, approval.id, "approve"))

    resumed = await _collect(
        runner.run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                resume=True,
            )
        )
    )

    assert resumed[-1].kind is AgentYieldKind.FINAL
    restored_user = next(
        message
        for message in model.requests[1].messages
        if message.role is ModelMessageRole.USER
    )
    assert restored_user.content == (TextPart("describe"), image, remote)


async def test_durable_multimodal_checkpoint_rejects_tampered_base64(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed persisted inline media cannot reach the provider on resume."""
    state_id = "multimodal-tampered"
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    target = ProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                attachments=(ImagePart.from_bytes(b"image", media_type="image/png"),),
            )
        )
    )
    current = states.get(state_id)
    checkpoint = cast(
        Mapping[str, JsonValue],
        current.metadata[RUNNER_CHECKPOINT_METADATA_KEY],
    )
    history = [
        dict(item)
        for item in cast(list[Mapping[str, JsonValue]], checkpoint["history"])
    ]
    user = next(item for item in history if item["role"] == "user")
    content = [
        dict(item) for item in cast(list[Mapping[str, JsonValue]], user["content"])
    ]
    media = next(item for item in content if item["type"] == "image")
    media["data"] = "%%%%%%%%"
    user["content"] = cast(JsonValue, content)
    forged: JsonObject = {**checkpoint, "history": history}
    states.save(
        replace(
            current,
            metadata={
                **current.metadata,
                RUNNER_CHECKPOINT_METADATA_KEY: forged,
            },
        )
    )

    def forbidden_decode(value: object, *, validate: bool) -> bytes:
        _ = (value, validate)
        raise AssertionError("checkpoint media decoded before evidence validation")

    monkeypatch.setattr(content_module, "b64decode", forbidden_decode)

    items = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                resume=True,
            )
        )
    )

    assert isinstance(items[-1].payload, Error)
    assert items[-1].payload.code == "agent_checkpoint_invalid"
    assert len(model.requests) == 1


async def test_checkpoint_cannot_self_authorize_larger_media_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid base64 plus a widened persisted limit still fails evidence binding."""
    state_id = "multimodal-widened"
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    target = ProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                attachments=(
                    ImagePart.from_bytes(
                        b"x",
                        media_type="image/png",
                        limits=MediaSafetyLimits(max_inline_bytes=1),
                    ),
                ),
            )
        )
    )
    current = states.get(state_id)
    checkpoint = cast(
        Mapping[str, JsonValue],
        current.metadata[RUNNER_CHECKPOINT_METADATA_KEY],
    )
    history = [
        dict(item)
        for item in cast(
            Sequence[Mapping[str, JsonValue]],
            checkpoint["history"],
        )
    ]
    user = next(item for item in history if item["role"] == "user")
    content = [
        dict(item)
        for item in cast(
            Sequence[Mapping[str, JsonValue]],
            user["content"],
        )
    ]
    media = next(item for item in content if item["type"] == "image")
    media["data"] = b64encode(b"replacement-body").decode("ascii")
    limits = cast(Mapping[str, JsonValue], media["limits"])
    media["limits"] = {**limits, "max_inline_bytes": 100}
    user["content"] = content
    forged: JsonObject = {
        **checkpoint,
        "history": history,
        "input_fingerprint": "forged-fingerprint",
    }
    states.save(
        replace(
            current,
            metadata={
                **current.metadata,
                RUNNER_CHECKPOINT_METADATA_KEY: forged,
            },
        )
    )

    def forbidden_decode(value: object, *, validate: bool) -> bytes:
        _ = (value, validate)
        raise AssertionError("widened checkpoint decoded before evidence validation")

    monkeypatch.setattr(content_module, "b64decode", forbidden_decode)

    items = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                resume=True,
            )
        )
    )

    assert isinstance(items[-1].payload, Error)
    assert items[-1].payload.code == "agent_checkpoint_invalid"
    assert len(model.requests) == 1


async def test_checkpoint_uri_tamper_rejected_before_media_reconstruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw checkpoint evidence is checked before reconstructing a tampered URI."""
    state_id = "multimodal-uri-tampered"
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    target = ProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                instruction="describe",
                attachments=(
                    ImagePart.from_uri(
                        "https://assets.example.test/original.png",
                        media_type="image/png",
                    ),
                ),
            )
        )
    )
    current = states.get(state_id)
    checkpoint = cast(
        Mapping[str, JsonValue],
        current.metadata[RUNNER_CHECKPOINT_METADATA_KEY],
    )
    history = [
        dict(item)
        for item in cast(Sequence[Mapping[str, JsonValue]], checkpoint["history"])
    ]
    user = next(item for item in history if item["role"] == "user")
    content = [
        dict(item) for item in cast(Sequence[Mapping[str, JsonValue]], user["content"])
    ]
    media = next(item for item in content if item["type"] == "image")
    media["uri"] = "https://private.example.invalid/secret.png"
    user["content"] = content
    states.save(
        replace(
            current,
            metadata={
                **current.metadata,
                RUNNER_CHECKPOINT_METADATA_KEY: {**checkpoint, "history": history},
            },
        )
    )

    def forbidden_media_class(kind: object) -> object:
        _ = kind
        raise AssertionError("checkpoint URI restored before evidence validation")

    monkeypatch.setattr(content_module, "_media_class", forbidden_media_class)
    items = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id=state_id, instruction="describe", resume=True)
        )
    )

    assert isinstance(items[-1].payload, Error)
    assert items[-1].payload.code == "agent_checkpoint_invalid"
    assert len(model.requests) == 1


async def test_checkpoint_revision_is_independent_of_repository_return_order() -> None:
    """Resume selects the highest unique revision, never sequence position."""
    state_id = "reordered-checkpoint-evidence"
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = ReorderedEvidenceRepository()
    first = ProbeAgent(model, states, signals, evidence)
    paused = await _collect(
        AgentRunner.for_agent_instance(first).run(
            RunAgentInput(state_id=state_id, instruction="write")
        )
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    signals.append(_approval_signal(state_id, approval.id, "approve"))

    resumed = await _collect(
        AgentRunner.for_agent_instance(
            ProbeAgent(model, states, signals, evidence)
        ).run(RunAgentInput(state_id=state_id, instruction="resume", resume=True))
    )

    assert resumed[-1].kind is AgentYieldKind.FINAL
    assert len(model.requests) == 2


async def test_checkpoint_revision_rejects_older_matching_replay() -> None:
    """An older valid checkpoint cannot replace the state after a newer save."""
    state_id = "stale-checkpoint-replay"
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    target = ProbeAgent(model, states, signals, evidence)
    paused = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id=state_id, instruction="write")
        )
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    old_checkpoint = cast(
        Mapping[str, JsonValue],
        states.get(state_id).metadata[RUNNER_CHECKPOINT_METADATA_KEY],
    )
    signals.append(_approval_signal(state_id, approval.id, "approve"))
    await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id=state_id, instruction="resume", resume=True)
        )
    )
    runner = AgentRunner.for_agent_instance(target)

    with pytest.raises(AgentDefinitionError, match="revision"):
        runner._validate_restored_checkpoint(state_id, old_checkpoint)


async def test_checkpoint_resume_rejects_conversation_switch() -> None:
    """A resumed state cannot append its original turn to a different conversation."""
    state_id = "checkpoint-conversation"
    model = MultimodalScriptedModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    target = ProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                conversation_id="original-conversation",
                instruction="write",
            )
        )
    )

    resumed = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                conversation_id="different-conversation",
                instruction="resume",
                resume=True,
            )
        )
    )

    assert isinstance(resumed[-1].payload, Error)
    assert resumed[-1].payload.code == "agent_checkpoint_invalid"
    assert len(model.requests) == 1


def _input_evidence_fixture(
    decisions: Sequence[object],
    *,
    context_length: int = 1,
    context_fingerprint: str | None = None,
) -> tuple[AgentRunner, runner_module._ExecutionContext, str]:
    state_id = "input-evidence"
    history = [ModelMessage.user("original")]
    fingerprint = runner_module._history_fingerprint(history)
    evidence = FakeEvidenceRepository()
    for index, decision in enumerate(decisions):
        evidence.append(
            AgentEvidence(
                id=f"model:{index}",
                agent_state_id=state_id,
                kind=AgentEvidenceKind.MODEL,
                payload=cast(JsonObject, {"decision": decision}),
            )
        )
    target = ProbeAgent(
        ScriptedRoundModel(()),
        FakeStateRepository(),
        FakeSignalRepository(()),
        evidence,
    )
    context = runner_module._ExecutionContext(
        state_id=state_id,
        history=history,
        step_count=1,
        initial_history_length=context_length,
        input_fingerprint=(
            fingerprint if context_fingerprint is None else context_fingerprint
        ),
    )
    return AgentRunner.for_agent_instance(target), context, fingerprint


def test_restored_input_accepts_exact_model_evidence_binding() -> None:
    """A complete exact step set and initial-transcript digest resumes cleanly."""
    _, _, fingerprint = _input_evidence_fixture(())
    runner, context, _ = _input_evidence_fixture(
        (
            {
                "initial_history_length": 1,
                "input_fingerprint": fingerprint,
                "step": 1,
            },
        )
    )

    runner._validate_restored_input(context.state_id, context)


@pytest.mark.parametrize(
    "decision",
    [
        "not-an-object",
        {"initial_history_length": True, "input_fingerprint": "x", "step": 1},
        {"initial_history_length": "1", "input_fingerprint": "x", "step": 1},
        {"initial_history_length": 0, "input_fingerprint": "x", "step": 1},
        {"initial_history_length": 1, "input_fingerprint": 1, "step": 1},
        {"initial_history_length": 1, "input_fingerprint": " ", "step": 1},
        {"initial_history_length": 1, "input_fingerprint": "x", "step": True},
        {"initial_history_length": 1, "input_fingerprint": "x", "step": "1"},
        {"initial_history_length": 1, "input_fingerprint": "x", "step": 0},
    ],
)
def test_restored_input_rejects_malformed_model_evidence(decision: object) -> None:
    """Every untrusted MODEL evidence scalar is validated before comparison."""
    runner, context, _ = _input_evidence_fixture((decision,))

    with pytest.raises(AgentDefinitionError):
        runner._validate_restored_input(context.state_id, context)


def test_restored_input_rejects_duplicate_model_step_evidence() -> None:
    """Duplicate append-only MODEL evidence cannot satisfy exact step coverage."""
    _, _, fingerprint = _input_evidence_fixture(())
    decision = {
        "initial_history_length": 1,
        "input_fingerprint": fingerprint,
        "step": 1,
    }
    runner, context, _ = _input_evidence_fixture((decision, decision))

    with pytest.raises(AgentDefinitionError):
        runner._validate_restored_input(context.state_id, context)


@pytest.mark.parametrize(
    "decisions",
    [(), ({"initial_history_length": 1, "input_fingerprint": "x", "step": 2},)],
)
def test_restored_input_rejects_incomplete_model_step_evidence(
    decisions: Sequence[object],
) -> None:
    """Missing evidence and a noncontiguous step set both fail closed."""
    runner, context, _ = _input_evidence_fixture(decisions)

    with pytest.raises(AgentDefinitionError, match="inconsistent"):
        runner._validate_restored_input(context.state_id, context)


@pytest.mark.parametrize(
    (
        "evidence_length",
        "evidence_fingerprint",
        "context_length",
        "context_fingerprint",
    ),
    [
        (1, "exact", 2, "exact"),
        (1, "exact", 1, "different"),
    ],
)
def test_restored_input_rejects_checkpoint_and_evidence_mismatch(
    evidence_length: int,
    evidence_fingerprint: str,
    context_length: int,
    context_fingerprint: str,
) -> None:
    """Checkpoint-carried input identifiers must match append-only MODEL evidence."""
    _, _, actual = _input_evidence_fixture(())
    evidence_value = actual if evidence_fingerprint == "exact" else evidence_fingerprint
    context_value = actual if context_fingerprint == "exact" else context_fingerprint
    runner, context, _ = _input_evidence_fixture(
        (
            {
                "initial_history_length": evidence_length,
                "input_fingerprint": evidence_value,
                "step": 1,
            },
        ),
        context_length=context_length,
        context_fingerprint=context_value,
    )

    with pytest.raises(AgentDefinitionError, match="does not match"):
        runner._validate_restored_input(context.state_id, context)


@pytest.mark.parametrize(
    "value",
    [
        float("inf"),
        cast(JsonValue, {1: "invalid-key"}),
        cast(JsonValue, object()),
    ],
)
def test_input_fingerprint_rejects_non_json_values(value: JsonValue) -> None:
    """Nonfinite numbers, non-string keys, and arbitrary objects stay out of hashes."""
    with pytest.raises(AgentDefinitionError):
        runner_module._fingerprint_json_value(value)


def test_input_fingerprint_preserves_finite_float() -> None:
    """Finite JSON numbers retain their value in the canonical hash payload."""
    assert runner_module._fingerprint_json_value(1.5) == 1.5


def test_input_fingerprint_rejects_recursive_metadata() -> None:
    """Recursive caller metadata is normalized into a typed definition failure."""
    recursive: dict[str, JsonValue] = {}
    recursive["self"] = recursive
    message = ModelMessage.user("original")
    object.__setattr__(message, "metadata", recursive)

    with pytest.raises(AgentDefinitionError, match="finite JSON"):
        runner_module._history_fingerprint((message,))


@pytest.mark.parametrize(
    "value",
    [
        {"role": 1, "content": "x", "metadata": {}},
        {"role": "user", "content": "x", "metadata": []},
        {"role": "invalid", "content": "x", "metadata": {}},
    ],
)
def test_checkpoint_message_helper_rejects_malformed_value(
    value: Mapping[str, JsonValue],
) -> None:
    """Checkpoint message role and metadata failures remain typed."""
    with pytest.raises(AgentDefinitionError):
        runner_module._message_from_metadata(value)


@pytest.mark.parametrize(
    "value",
    [
        {"name": 1, "arguments": {}, "call_id": None, "metadata": {}},
        {"name": "tool", "arguments": {}, "call_id": 1, "metadata": {}},
        {"name": "tool", "arguments": {}, "call_id": None, "metadata": []},
    ],
)
def test_checkpoint_tool_call_helper_rejects_malformed_value(
    value: Mapping[str, JsonValue],
) -> None:
    """Checkpoint tool-call identity, correlation, and metadata are validated."""
    with pytest.raises(AgentDefinitionError):
        runner_module._call_from_metadata(value)


def test_checkpoint_collection_helpers_reject_malformed_values() -> None:
    """Generic checkpoint sequence, mapping, and counter helpers fail closed."""
    with pytest.raises(AgentDefinitionError):
        runner_module._mapping_sequence({"value": "bad"}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._mapping_sequence({"value": ["bad"]}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._string_sequence({"value": "bad"}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._string_sequence({"value": [1]}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._mapping_metadata({"value": []}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._integer_metadata({"value": True}, "value")


def _checkpoint_validation_fixture() -> tuple[
    AgentRunner,
    JsonObject,
    FakeEvidenceRepository,
]:
    state_id = "checkpoint-validation"
    history = [ModelMessage.user("original")]
    context = runner_module._ExecutionContext(
        state_id=state_id,
        history=history,
        step_count=1,
        initial_history_length=1,
        input_fingerprint=runner_module._history_fingerprint(history),
        checkpoint_revision=1,
    )
    checkpoint = runner_module._context_metadata(context)
    fingerprint = runner_module._json_fingerprint(checkpoint)
    evidence = FakeEvidenceRepository()
    evidence.append(
        AgentEvidence(
            id="checkpoint:1",
            agent_state_id=state_id,
            kind=AgentEvidenceKind.CHECKPOINT,
            payload={
                "revision": 1,
                "step": 1,
                "history_length": 1,
                "shape_size": runner_module._checkpoint_shape_size(checkpoint),
                "fingerprint": fingerprint,
            },
        )
    )
    runner = AgentRunner.for_agent_instance(
        ProbeAgent(
            ScriptedRoundModel(()),
            FakeStateRepository(),
            FakeSignalRepository(()),
            evidence,
        )
    )
    return runner, checkpoint, evidence


def test_checkpoint_validation_accepts_exact_latest_revision() -> None:
    """The raw JSON, revision, shape, and digest can match independently of order."""
    runner, checkpoint, _ = _checkpoint_validation_fixture()

    runner._validate_restored_checkpoint("checkpoint-validation", checkpoint)


@pytest.mark.parametrize("revision", [True, 0, "1"])
def test_checkpoint_validation_rejects_invalid_evidence_revision(
    revision: object,
) -> None:
    """Checkpoint evidence revisions are unique positive integers."""
    runner, checkpoint, evidence = _checkpoint_validation_fixture()
    artifact = evidence.get("checkpoint:1")
    evidence.append(
        replace(
            artifact,
            payload={**artifact.payload, "revision": cast(JsonValue, revision)},
        )
    )

    with pytest.raises(AgentDefinitionError, match="revision"):
        runner._validate_restored_checkpoint("checkpoint-validation", checkpoint)


def test_checkpoint_validation_rejects_duplicate_revision() -> None:
    """Two receipts cannot claim authority for the same checkpoint revision."""
    runner, checkpoint, evidence = _checkpoint_validation_fixture()
    artifact = evidence.get("checkpoint:1")
    evidence.append(replace(artifact, id="checkpoint:duplicate"))

    with pytest.raises(AgentDefinitionError, match="revision"):
        runner._validate_restored_checkpoint("checkpoint-validation", checkpoint)


@pytest.mark.parametrize(
    ("payload_update", "checkpoint_update"),
    [
        ({"fingerprint": 1}, {}),
        ({"fingerprint": " "}, {}),
        ({"shape_size": True}, {}),
        ({"shape_size": "1"}, {}),
        ({"shape_size": 0}, {}),
        ({"history_length": True}, {}),
        ({"history_length": "1"}, {}),
        ({"history_length": 0}, {}),
        ({"step": True}, {}),
        ({"step": "1"}, {}),
        ({"step": 0}, {}),
        ({}, {"history": "bad"}),
        ({}, {"step_count": True}),
        ({}, {"step_count": "1"}),
    ],
)
def test_checkpoint_validation_rejects_malformed_receipt_fields(
    payload_update: Mapping[str, JsonValue],
    checkpoint_update: Mapping[str, JsonValue],
) -> None:
    """Every raw checkpoint and trusted receipt scalar is validated before restore."""
    runner, checkpoint, evidence = _checkpoint_validation_fixture()
    artifact = evidence.get("checkpoint:1")
    evidence.append(replace(artifact, payload={**artifact.payload, **payload_update}))

    with pytest.raises(AgentDefinitionError, match="evidence"):
        runner._validate_restored_checkpoint(
            "checkpoint-validation",
            {**checkpoint, **checkpoint_update},
        )


@pytest.mark.parametrize(
    ("payload_update", "expected"),
    [
        ({"history_length": 2}, "inconsistent"),
        ({"step": 2}, "inconsistent"),
        ({"shape_size": 1}, "shape"),
    ],
)
def test_checkpoint_validation_rejects_inconsistent_receipt(
    payload_update: Mapping[str, JsonValue],
    expected: str,
) -> None:
    """Well-typed but nonmatching checkpoint receipts also fail closed."""
    runner, checkpoint, evidence = _checkpoint_validation_fixture()
    artifact = evidence.get("checkpoint:1")
    evidence.append(replace(artifact, payload={**artifact.payload, **payload_update}))

    with pytest.raises(AgentDefinitionError, match=expected):
        runner._validate_restored_checkpoint("checkpoint-validation", checkpoint)


@pytest.mark.parametrize(
    "checkpoint_update",
    [
        {"static_context_fingerprint": 1},
        {"pricing_fingerprint": "priced"},
        {"initial_history_length": 0},
    ],
)
def test_context_restore_rejects_invalid_cross_field_checkpoint(
    checkpoint_update: Mapping[str, JsonValue],
) -> None:
    """Context, pricing, and input cross-fields remain typed after integrity checks."""
    runner, checkpoint, _ = _checkpoint_validation_fixture()

    with pytest.raises(AgentDefinitionError):
        runner._context_from_checkpoint(
            "checkpoint-validation",
            {**checkpoint, **checkpoint_update},
        )


def test_checkpoint_scalar_helpers_reject_invalid_text_and_decimal() -> None:
    """Optional checkpoint text and decimal values reject malformed runtime shapes."""
    with pytest.raises(AgentDefinitionError):
        runner_module._optional_checkpoint_text({"value": 1}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._required_checkpoint_text({}, "value")
    with pytest.raises(AgentDefinitionError):
        runner_module._boolean_metadata({"value": 1}, "value")
    for value in (1, "bad", "NaN", "-1"):
        with pytest.raises(AgentDefinitionError):
            runner_module._optional_checkpoint_decimal(
                {"value": cast(JsonValue, value)},
                "value",
            )


def test_checkpoint_json_helpers_reject_recursive_and_non_json_values() -> None:
    """Pre-decode shape and fingerprint helpers fail closed on hostile JSON shapes."""
    recursive: list[JsonValue] = []
    recursive.append(recursive)
    with pytest.raises(AgentDefinitionError):
        runner_module._json_fingerprint(recursive)
    with pytest.raises(AgentDefinitionError):
        runner_module._checkpoint_shape_size(recursive)
    assert runner_module._json_shape_size(1.5) == 1
    for value in (float("inf"), cast(JsonValue, {1: "bad"}), object()):
        with pytest.raises(AgentDefinitionError):
            runner_module._json_shape_size(value)


@pytest.mark.parametrize("restored", [False, True])
def test_pending_batch_authorization_normalizes_invalid_catalog(
    restored: bool,
) -> None:
    """Fresh and restored invalid pending batches use their distinct typed codes."""
    runner, context, _ = _input_evidence_fixture(())
    context.pending_calls = [ModelToolCall("missing.tool", {})]
    context.restored_from_checkpoint = restored

    result = runner._authorize_pending_batch(None, context)

    assert result.error is not None
    assert result.error.code == (
        "agent_checkpoint_invalid" if restored else "agent_approval_invalid"
    )
