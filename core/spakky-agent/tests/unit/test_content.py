"""Tests for portable immutable multimodal model content."""

from collections.abc import Callable, Sequence
from typing import cast

import pytest

import spakky.agent as agent_api
from spakky.agent.content import (
    DEFAULT_MEDIA_SAFETY_LIMITS,
    AudioPart,
    DocumentPart,
    ImagePart,
    MediaSafetyLimits,
    ModelContentPart,
    TextPart,
    VideoPart,
    model_content_parts,
    model_content_size,
    model_content_text,
    restore_model_content,
    serialize_model_content,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.interfaces.model import ModelMessage, ModelMessageRole

_SERIALIZED_LIMITS = {
    "max_inline_bytes": DEFAULT_MEDIA_SAFETY_LIMITS.max_inline_bytes,
    "max_media_parts": DEFAULT_MEDIA_SAFETY_LIMITS.max_media_parts,
    "allowed_uri_schemes": ("https",),
    "allowed_uri_hosts": None,
}


@pytest.mark.parametrize(
    ("factory", "media_type"),
    [
        (ImagePart, "image/png"),
        (AudioPart, "audio/mpeg"),
        (VideoPart, "video/mp4"),
        (DocumentPart, "application/pdf"),
    ],
)
def test_media_factories_remote_and_inline_expect_provenance_and_size(
    factory: type[ImagePart] | type[AudioPart] | type[VideoPart] | type[DocumentPart],
    media_type: str,
) -> None:
    """Each modality supports exactly one remote URI or bounded bytes source."""
    remote = factory.from_uri(
        "https://assets.example.test/input",
        media_type=media_type,
        source="upload:1",
        content_digest="sha256:one",
    )
    inline = factory.from_bytes(
        b"payload",
        media_type=media_type,
        source="upload:2",
        content_digest="sha256:two",
    )

    assert remote.uri == "https://assets.example.test/input"
    assert remote.safety_limits is DEFAULT_MEDIA_SAFETY_LIMITS
    assert remote.data is None
    assert remote.size is None
    assert inline.uri is None
    assert inline.data == b"payload"
    assert inline.size == 7
    assert inline.source == "upload:2"
    assert inline.content_digest == "sha256:two"


def test_document_factories_expect_optional_validated_filename() -> None:
    """Document filenames survive both URI and raw-byte construction."""
    remote = DocumentPart.from_uri(
        "https://assets.example.test/report.pdf",
        media_type="application/pdf",
        filename="report.pdf",
    )
    inline = DocumentPart.from_bytes(
        b"pdf",
        media_type="application/pdf",
        filename="inline.pdf",
    )

    assert remote.filename == "report.pdf"
    assert inline.filename == "inline.pdf"


def test_media_safety_limits_expect_replaceable_remote_scheme_and_byte_bound() -> None:
    """Callers may narrow/extend remote schemes while retaining an explicit byte cap."""
    limits = MediaSafetyLimits(
        max_inline_bytes=3,
        max_media_parts=2,
        allowed_uri_schemes=frozenset({"gs", "https"}),
    )

    part = ImagePart.from_uri(
        "gs://bucket/image.png",
        media_type="image/png",
        limits=limits,
    )

    assert part.uri == "gs://bucket/image.png"
    serialized = serialize_model_content((part,))
    assert serialize_model_content(restore_model_content(serialized)) == serialized
    with pytest.raises(AgentDefinitionError):
        ImagePart.from_bytes(
            b"four",
            media_type="image/png",
            limits=limits,
        )


def test_media_public_address_expect_valid_remote_uri() -> None:
    """A public absolute HTTPS address remains a valid no-fetch reference."""
    part = ImagePart.from_uri("https://8.8.8.8/image.png", media_type="image/png")

    assert part.uri == "https://8.8.8.8/image.png"
    mapped = ImagePart.from_uri(
        "https://[::ffff:8.8.8.8]/image.png",
        media_type="image/png",
    )
    assert mapped.uri == "https://[::ffff:8.8.8.8]/image.png"


@pytest.mark.parametrize(
    "factory",
    [
        # Runtime-boundary probes intentionally violate static annotations.
        lambda: MediaSafetyLimits(max_inline_bytes=cast(int, True)),
        lambda: MediaSafetyLimits(max_inline_bytes=0),
        lambda: MediaSafetyLimits(max_media_parts=cast(int, True)),
        lambda: MediaSafetyLimits(max_media_parts=0),
        lambda: MediaSafetyLimits(allowed_uri_schemes=cast(frozenset[str], {"https"})),
        lambda: MediaSafetyLimits(allowed_uri_schemes=frozenset()),
        lambda: MediaSafetyLimits(allowed_uri_schemes=frozenset({"HTTPS"})),
        lambda: MediaSafetyLimits(allowed_uri_schemes=frozenset({"file"})),
        lambda: MediaSafetyLimits(allowed_uri_schemes=frozenset({"data"})),
        lambda: MediaSafetyLimits(
            allowed_uri_hosts=cast(frozenset[str], {"assets.example.test"})
        ),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset()),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset({cast(str, 1)})),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset({""})),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset({"EXAMPLE.test"})),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset({"example.test."})),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset({"example .test"})),
        lambda: MediaSafetyLimits(allowed_uri_hosts=frozenset({"example.test/path"})),
    ],
)
def test_media_safety_limits_invalid_definition_expect_definition_error(
    factory: Callable[[], MediaSafetyLimits],
) -> None:
    """Limits cannot be nonpositive, mutable-shaped, malformed, or local."""
    with pytest.raises(AgentDefinitionError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ImagePart.from_uri("relative.png", media_type="image/png"),
        lambda: ImagePart.from_uri(
            "data:image/png;base64,AAAA", media_type="image/png"
        ),
        lambda: ImagePart.from_uri("file:///tmp/image.png", media_type="image/png"),
        lambda: ImagePart.from_uri(
            "http://assets.example.test/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            " https://assets.example.test/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://assets.example.test/\nimage.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://assets.example.test/\x00image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://user:secret@assets.example.test/image.png",
            media_type="image/png",
        ),
        lambda: ImagePart.from_uri(
            "https://localhost/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://localhost./image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://2130706433/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://999999999999999999999/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://0x7f000001/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://0xffffffffffffffffffff/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://0xnothex/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri("https://127.1/image.png", media_type="image/png"),
        lambda: ImagePart.from_uri(
            "https://127.0.0.1.nip.io/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://service.local/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://127.0.0.1/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://10.0.0.1/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://224.0.0.1/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://239.255.255.250/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://[ff02::1]/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://[::ffff:127.0.0.1]/image.png", media_type="image/png"
        ),
        lambda: ImagePart.from_uri(
            "https://assets.example.test:invalid/image.png",
            media_type="image/png",
        ),
    ],
)
def test_media_uri_security_boundary_expect_definition_error(
    factory: Callable[[], ImagePart],
) -> None:
    """Relative, inline, local, credentialed, and malformed URIs are rejected."""
    with pytest.raises(AgentDefinitionError):
        factory()


def test_media_uri_host_allowlist_expect_exact_operator_authority() -> None:
    """An explicit host allowlist bypasses ambient DNS and rejects every other host."""
    limits = MediaSafetyLimits(allowed_uri_hosts=frozenset({"assets.example.test"}))

    accepted = ImagePart.from_uri(
        "https://assets.example.test./image.png",
        media_type="image/png",
        limits=limits,
    )

    assert accepted.uri == "https://assets.example.test./image.png"
    with pytest.raises(AgentDefinitionError, match="not authorized"):
        ImagePart.from_uri(
            "https://other.example.test/image.png",
            media_type="image/png",
            limits=limits,
        )


def test_media_uri_hostname_construction_is_side_effect_free() -> None:
    """A hostname is stored as a value; async adapters own any network resolution."""
    part = ImagePart.from_uri(
        "https://dynamic.example.invalid/image.png",
        media_type="image/png",
    )

    assert part.uri == "https://dynamic.example.invalid/image.png"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ImagePart.from_uri(
            "https://assets.example.test/image", media_type="audio/mpeg"
        ),
        lambda: AudioPart.from_bytes(b"audio", media_type="image/png"),
        lambda: VideoPart.from_bytes(b"video", media_type="application/octet-stream"),
        lambda: DocumentPart.from_bytes(b"doc", media_type="image/png"),
        lambda: ImagePart.from_bytes(b"image", media_type="IMAGE/PNG"),
        lambda: ImagePart.from_bytes(b"image", media_type="image/png; charset=x"),
        lambda: ImagePart.from_bytes(b"", media_type="image/png"),
        lambda: ImagePart(
            media_type="image/png",
            uri="https://assets.example.test/image.png",
            data=b"image",
        ),
        lambda: ImagePart(media_type="image/png"),
        lambda: ImagePart.from_bytes(
            cast(bytes, bytearray(b"image")), media_type="image/png"
        ),
        lambda: ImagePart.from_bytes(
            b"image", media_type="image/png", source="line\nbreak"
        ),
        lambda: ImagePart.from_bytes(
            b"image", media_type="image/png", content_digest=" "
        ),
        lambda: ImagePart.from_bytes(
            b"image",
            media_type="image/png",
            limits=cast(MediaSafetyLimits, object()),
        ),
        lambda: DocumentPart.from_bytes(
            b"document", media_type="application/pdf", filename="line\nbreak"
        ),
    ],
)
def test_media_malformed_source_mime_and_provenance_expect_definition_error(
    factory: Callable[[], object],
) -> None:
    """MIME, source exclusivity, bytes, provenance, and filename fail closed."""
    with pytest.raises(AgentDefinitionError):
        factory()


def test_model_message_multipart_input_expect_immutable_tuple_snapshot() -> None:
    """A mutable caller sequence cannot change the message after construction."""
    parts: list[ModelContentPart] = [TextPart("describe")]
    message = ModelMessage(ModelMessageRole.USER, parts)
    parts.append(
        ImagePart.from_uri(
            "https://assets.example.test/later.png",
            media_type="image/png",
        )
    )

    assert message.content == (TextPart("describe"),)
    assert ModelMessage.user("텍스트만") == ModelMessage(
        ModelMessageRole.USER,
        "텍스트만",
    )
    with pytest.raises(AgentDefinitionError):
        TextPart(cast(str, 1))


def test_model_message_enforces_total_inline_bytes_and_media_count() -> None:
    """Many individually valid parts cannot bypass one bounded message budget."""
    limits = MediaSafetyLimits(max_inline_bytes=3, max_media_parts=2)
    inline = ImagePart.from_bytes(b"ab", media_type="image/png", limits=limits)
    remote = ImagePart.from_uri(
        "https://assets.example.test/image.png",
        media_type="image/png",
        limits=limits,
    )

    with pytest.raises(AgentDefinitionError, match="total inline"):
        ModelMessage.user((inline, inline))
    with pytest.raises(AgentDefinitionError, match="too many"):
        ModelMessage.user((remote, remote, remote))


def test_model_content_serialization_expect_exact_round_trip() -> None:
    """Checkpoint serialization preserves ordered types, bytes, and provenance."""
    content = (
        TextPart("explain"),
        ImagePart.from_uri(
            "https://assets.example.test/chart.png",
            media_type="image/png",
            source="chart:1",
        ),
        AudioPart.from_bytes(b"audio", media_type="audio/mpeg"),
        VideoPart.from_bytes(b"video", media_type="video/mp4"),
        DocumentPart.from_uri(
            "https://assets.example.test/remote.pdf",
            media_type="application/pdf",
            filename="remote.pdf",
        ),
        DocumentPart.from_bytes(
            b"document",
            media_type="application/pdf",
            filename="report.pdf",
            content_digest="sha256:doc",
        ),
    )

    serialized = serialize_model_content(content)
    restored = restore_model_content(serialized)

    assert restored == content
    assert serialize_model_content("plain") == "plain"
    assert restore_model_content("plain") == "plain"
    assert isinstance(serialized, tuple)
    assert serialized[-1] == {
        "type": "document",
        "media_type": "application/pdf",
        "limits": _SERIALIZED_LIMITS,
        "data": "ZG9jdW1lbnQ=",
        "content_digest": "sha256:doc",
        "filename": "report.pdf",
    }


def test_model_content_text_and_size_expect_no_invented_media_description() -> None:
    """Helpers expose only real text and known inline bytes, never fetched URI size."""
    content = (
        TextPart("a"),
        ImagePart.from_uri(
            "https://assets.example.test/image.png",
            media_type="image/png",
        ),
        TextPart("한"),
        AudioPart.from_bytes(b"1234", media_type="audio/mpeg"),
    )

    assert model_content_text(content) == "a한"
    assert model_content_size(content) == len("a한".encode()) + 4
    assert model_content_text("plain") == "plain"
    assert model_content_size("한") == len("한".encode())
    assert model_content_parts("plain") == (TextPart("plain"),)


@pytest.mark.parametrize(
    "value",
    [
        object(),
        (),
        ("not-an-object",),
        ({"type": "unknown"},),
        ({"type": "text", "text": 1},),
        ({"type": "text", "text": "ok", "extra": True},),
        ({"type": "image", "media_type": "image/png", "extra": True},),
        ({"type": "image", "uri": "https://assets.example.test/image.png"},),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "uri": "https://assets.example.test/image.png",
                "data": "aW1hZ2U=",
                "limits": _SERIALIZED_LIMITS,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "%%%",
                "limits": _SERIALIZED_LIMITS,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "",
                "limits": _SERIALIZED_LIMITS,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "source": 1,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "content_digest": 1,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "filename": "wrong.png",
            },
        ),
        (
            {
                "type": "document",
                "media_type": "application/pdf",
                "data": "ZG9j",
                "filename": 1,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "limits": _SERIALIZED_LIMITS,
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {"unknown": True},
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": True,
                    "max_media_parts": 16,
                    "allowed_uri_schemes": ("https",),
                    "allowed_uri_hosts": None,
                },
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": 10,
                    "max_media_parts": 16,
                    "allowed_uri_schemes": "https",
                    "allowed_uri_hosts": None,
                },
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": 10,
                    "max_media_parts": 16,
                    "allowed_uri_schemes": (1,),
                    "allowed_uri_hosts": None,
                },
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": 10,
                    "max_media_parts": True,
                    "allowed_uri_schemes": ("https",),
                    "allowed_uri_hosts": None,
                },
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": 10,
                    "max_media_parts": 16,
                    "allowed_uri_schemes": ("https",),
                    "allowed_uri_hosts": "assets.example.test",
                },
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": 10,
                    "max_media_parts": 16,
                    "allowed_uri_schemes": ("https",),
                    "allowed_uri_hosts": (1,),
                },
            },
        ),
        (
            {
                "type": "image",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
                "limits": {
                    "max_inline_bytes": 3,
                    "max_media_parts": 16,
                    "allowed_uri_schemes": ("https",),
                    "allowed_uri_hosts": None,
                },
            },
        ),
    ],
)
def test_restore_model_content_malformed_payload_expect_definition_error(
    value: object,
) -> None:
    """Malformed checkpoint types, fields, source, and base64 never restore."""
    with pytest.raises(AgentDefinitionError):
        restore_model_content(value)


def test_content_public_exports_expect_canonical_identity() -> None:
    """The root surface exposes only the promised parts and replaceable limits."""
    assert agent_api.TextPart is TextPart
    assert agent_api.ImagePart is ImagePart
    assert agent_api.AudioPart is AudioPart
    assert agent_api.VideoPart is VideoPart
    assert agent_api.DocumentPart is DocumentPart
    assert agent_api.MediaSafetyLimits is MediaSafetyLimits
    assert agent_api.DEFAULT_MEDIA_SAFETY_LIMITS is DEFAULT_MEDIA_SAFETY_LIMITS


def test_model_content_invalid_sequence_expect_definition_error() -> None:
    """Content normalization rejects empty, byte, and unknown part sequences."""
    # Runtime-boundary probes intentionally violate static annotations.
    values = (
        (),
        cast(Sequence[ModelContentPart], b"bytes"),
        cast(Sequence[ModelContentPart], (object(),)),
    )
    for value in values:
        with pytest.raises(AgentDefinitionError):
            model_content_parts(value)


def test_serialize_model_content_tampered_inline_source_expect_definition_error() -> (
    None
):
    """A corrupted in-memory media object cannot silently serialize empty bytes."""
    part = ImagePart.from_bytes(b"image", media_type="image/png")
    object.__setattr__(part, "data", None)

    with pytest.raises(AgentDefinitionError):
        serialize_model_content((part,))
