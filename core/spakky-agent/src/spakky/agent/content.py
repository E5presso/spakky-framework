"""Portable immutable multimodal model-content contracts."""

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address, ip_address
from re import fullmatch
from typing import ClassVar, Self, override
from urllib.parse import urlsplit

from spakky.agent.error import AgentDefinitionError
from spakky.agent.types import JsonObject, JsonValue

_MEBIBYTE = 1024 * 1024
_MIME_PATTERN = r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*"
_SCHEME_PATTERN = r"[a-z][a-z0-9+.-]*"
_FORBIDDEN_URI_SCHEMES = frozenset({"data", "file"})
_LOCAL_RESOLVER_SUFFIXES = (".nip.io", ".sslip.io", ".localtest.me")


@dataclass(frozen=True, slots=True)
class MediaSafetyLimits:
    """Replaceable vendor-neutral limits applied when media enters the model port."""

    max_inline_bytes: int = 20 * _MEBIBYTE
    max_media_parts: int = 16
    allowed_uri_schemes: frozenset[str] = frozenset({"https"})
    allowed_uri_hosts: frozenset[str] | None = None

    def __post_init__(self) -> None:
        """Reject unbounded or malformed media limits."""
        if (
            isinstance(self.max_inline_bytes, bool)
            or not isinstance(self.max_inline_bytes, int)
            or self.max_inline_bytes <= 0
        ):
            raise AgentDefinitionError("Inline media byte limit must be positive")
        if (
            isinstance(self.max_media_parts, bool)
            or not isinstance(self.max_media_parts, int)
            or self.max_media_parts <= 0
        ):
            raise AgentDefinitionError("Media part limit must be positive")
        if (
            not isinstance(self.allowed_uri_schemes, frozenset)
            or not self.allowed_uri_schemes
        ):
            raise AgentDefinitionError("Media URI schemes must be a nonempty frozenset")
        for scheme in self.allowed_uri_schemes:
            if (
                not isinstance(scheme, str)
                or fullmatch(_SCHEME_PATTERN, scheme) is None
                or scheme in _FORBIDDEN_URI_SCHEMES
            ):
                raise AgentDefinitionError("Media URI scheme is invalid")
        if self.allowed_uri_hosts is not None:
            if (
                not isinstance(self.allowed_uri_hosts, frozenset)
                or not self.allowed_uri_hosts
            ):
                raise AgentDefinitionError(
                    "Media URI hosts must be a nonempty frozenset"
                )
            for host in self.allowed_uri_hosts:
                if (
                    not isinstance(host, str)
                    or host == ""
                    or host != host.rstrip(".").casefold()
                    or any(character.isspace() for character in host)
                    or any(character in host for character in "/@?#")
                ):
                    raise AgentDefinitionError("Media URI host authority is invalid")


DEFAULT_MEDIA_SAFETY_LIMITS = MediaSafetyLimits()
"""Conservative default: HTTPS references and at most 20 MiB inline bytes."""


@dataclass(frozen=True, slots=True)
class TextPart:
    """One ordered text segment inside a multimodal model message."""

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise AgentDefinitionError("Model text part must contain text")


@dataclass(frozen=True, slots=True)
class _MediaPart:
    """Shared exactly-one-source storage for public media parts."""

    media_type: str
    uri: str | None = None
    data: bytes | None = None
    source: str | None = None
    content_digest: str | None = None
    _limits: MediaSafetyLimits = field(
        default=DEFAULT_MEDIA_SAFETY_LIMITS,
        repr=False,
        compare=False,
    )

    _MIME_PREFIXES: ClassVar[tuple[str, ...]] = ()
    _KIND: ClassVar[str]

    def __post_init__(self) -> None:
        """Validate MIME, provenance, source exclusivity, URI, and inline size."""
        if (
            not isinstance(self.media_type, str)
            or fullmatch(_MIME_PATTERN, self.media_type) is None
            or not self.media_type.startswith(self._MIME_PREFIXES)
        ):
            raise AgentDefinitionError("Model media MIME type is invalid")
        if not isinstance(self._limits, MediaSafetyLimits):
            raise AgentDefinitionError("Model media safety limits are invalid")
        if (self.uri is None) == (self.data is None):
            raise AgentDefinitionError("Model media must declare exactly one source")
        for value in (self.source, self.content_digest):
            if value is not None:
                self._validate_provenance(value)
        if self.uri is not None:
            self._validate_uri(self.uri)
            return
        if not isinstance(self.data, bytes) or len(self.data) == 0:
            raise AgentDefinitionError("Inline model media must contain bytes")
        if len(self.data) > self._limits.max_inline_bytes:
            raise AgentDefinitionError("Inline model media exceeds its byte limit")

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        media_type: str,
        source: str | None = None,
        content_digest: str | None = None,
        limits: MediaSafetyLimits = DEFAULT_MEDIA_SAFETY_LIMITS,
    ) -> Self:
        """Create media from one absolute remote URI without fetching it."""
        return cls(
            media_type=media_type,
            uri=uri,
            source=source,
            content_digest=content_digest,
            _limits=limits,
        )

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        media_type: str,
        source: str | None = None,
        content_digest: str | None = None,
        limits: MediaSafetyLimits = DEFAULT_MEDIA_SAFETY_LIMITS,
    ) -> Self:
        """Create media from immutable raw bytes bounded before base64 encoding."""
        return cls(
            media_type=media_type,
            data=data,
            source=source,
            content_digest=content_digest,
            _limits=limits,
        )

    @property
    def size(self) -> int | None:
        """Return known inline byte size; remote resource size remains unknown."""
        return None if self.data is None else len(self.data)

    @property
    def safety_limits(self) -> MediaSafetyLimits:
        """Return the immutable policy snapshot carried with this media part."""
        return self._limits

    def _validate_uri(self, value: object) -> None:
        if (
            not isinstance(value, str)
            or value.strip() != value
            or value == ""
            or any(
                character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
                for character in value
            )
        ):
            raise AgentDefinitionError("Model media URI is invalid")
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            parsed.port
        except ValueError as error:
            raise AgentDefinitionError("Model media URI is invalid") from error
        if (
            parsed.scheme not in self._limits.allowed_uri_schemes
            or parsed.scheme in _FORBIDDEN_URI_SCHEMES
            or parsed.netloc == ""
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise AgentDefinitionError("Model media URI must be an allowed remote URI")
        normalized_host = hostname.rstrip(".").casefold()
        if self._limits.allowed_uri_hosts is not None:
            if normalized_host not in self._limits.allowed_uri_hosts:
                raise AgentDefinitionError("Model media URI host is not authorized")
            return
        if (
            normalized_host == "localhost"
            or normalized_host.endswith((".localhost", ".local"))
            or normalized_host.endswith(_LOCAL_RESOLVER_SUFFIXES)
        ):
            raise AgentDefinitionError("Model media URI cannot target a local host")
        if parsed.scheme not in {"http", "https"}:
            return
        try:
            address = ip_address(normalized_host)
        except ValueError:
            if normalized_host.isdecimal():
                numeric_address = int(normalized_host)
                if numeric_address > 0xFFFFFFFF:
                    raise AgentDefinitionError("Model media URI address is invalid")
                address = ip_address(numeric_address)
            elif normalized_host.startswith("0x"):
                try:
                    numeric_address = int(normalized_host, 16)
                except ValueError as error:
                    raise AgentDefinitionError(
                        "Model media URI address is invalid"
                    ) from error
                if numeric_address > 0xFFFFFFFF:
                    raise AgentDefinitionError("Model media URI address is invalid")
                address = ip_address(numeric_address)
            elif all(
                character.isdigit() or character == "." for character in normalized_host
            ):
                raise AgentDefinitionError("Model media URI address is invalid")
            else:
                return
        if not _is_public_media_address(address):
            raise AgentDefinitionError("Model media URI cannot target a local address")

    @staticmethod
    def _validate_provenance(value: object) -> None:
        if (
            not isinstance(value, str)
            or value.strip() == ""
            or "\n" in value
            or "\r" in value
        ):
            raise AgentDefinitionError(
                "Model media provenance must be nonblank single-line text"
            )


@dataclass(frozen=True, slots=True)
class ImagePart(_MediaPart):
    """Portable image input from a remote URI or bounded inline bytes."""

    _MIME_PREFIXES: ClassVar[tuple[str, ...]] = ("image/",)
    _KIND: ClassVar[str] = "image"


@dataclass(frozen=True, slots=True)
class AudioPart(_MediaPart):
    """Portable audio input from a remote URI or bounded inline bytes."""

    _MIME_PREFIXES: ClassVar[tuple[str, ...]] = ("audio/",)
    _KIND: ClassVar[str] = "audio"


@dataclass(frozen=True, slots=True)
class VideoPart(_MediaPart):
    """Portable video input where a selected provider supports it."""

    _MIME_PREFIXES: ClassVar[tuple[str, ...]] = ("video/",)
    _KIND: ClassVar[str] = "video"


@dataclass(frozen=True, slots=True)
class DocumentPart(_MediaPart):
    """Portable application/text document input with explicit MIME provenance."""

    filename: str | None = None

    _MIME_PREFIXES: ClassVar[tuple[str, ...]] = ("application/", "text/")
    _KIND: ClassVar[str] = "document"

    @override
    def __post_init__(self) -> None:
        _MediaPart.__post_init__(self)
        if self.filename is not None:
            self._validate_filename(self.filename)

    @classmethod
    @override
    def from_uri(
        cls,
        uri: str,
        *,
        media_type: str,
        filename: str | None = None,
        source: str | None = None,
        content_digest: str | None = None,
        limits: MediaSafetyLimits = DEFAULT_MEDIA_SAFETY_LIMITS,
    ) -> Self:
        """Create a remote document with optional provider-facing filename."""
        return cls(
            media_type=media_type,
            uri=uri,
            filename=filename,
            source=source,
            content_digest=content_digest,
            _limits=limits,
        )

    @classmethod
    @override
    def from_bytes(
        cls,
        data: bytes,
        *,
        media_type: str,
        filename: str | None = None,
        source: str | None = None,
        content_digest: str | None = None,
        limits: MediaSafetyLimits = DEFAULT_MEDIA_SAFETY_LIMITS,
    ) -> Self:
        """Create an inline document with optional provider-facing filename."""
        return cls(
            media_type=media_type,
            data=data,
            filename=filename,
            source=source,
            content_digest=content_digest,
            _limits=limits,
        )

    @staticmethod
    def _validate_filename(value: object) -> None:
        if (
            not isinstance(value, str)
            or value.strip() == ""
            or "\n" in value
            or "\r" in value
        ):
            raise AgentDefinitionError(
                "Model document filename must be nonblank single-line text"
            )


type ModelContentPart = TextPart | ImagePart | AudioPart | VideoPart | DocumentPart
type ModelContent = str | Sequence[ModelContentPart]
_CONTENT_PART_TYPES = (TextPart, ImagePart, AudioPart, VideoPart, DocumentPart)


def _is_public_media_address(address: IPv4Address | IPv6Address) -> bool:
    if address.is_multicast or not address.is_global:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        mapped = address.ipv4_mapped
        return mapped.is_global and not mapped.is_multicast
    return True


def model_content_parts(content: ModelContent) -> tuple[ModelContentPart, ...]:
    """Normalize legacy text or an already snapshotted sequence to ordered parts."""
    if isinstance(content, str):
        return (TextPart(content),)
    if not isinstance(content, Sequence) or isinstance(content, bytes | bytearray):
        raise AgentDefinitionError(
            "Model message content must be text or content parts"
        )
    parts = tuple(content)
    if not parts or any(not isinstance(part, _CONTENT_PART_TYPES) for part in parts):
        raise AgentDefinitionError("Model message content parts are invalid")
    _validate_media_budget(parts)
    return parts


def validate_model_content_budget(contents: Sequence[ModelContent]) -> None:
    """Enforce one aggregate media budget across a complete model request."""
    parts = tuple(part for content in contents for part in model_content_parts(content))
    _validate_media_budget(parts)


def _validate_media_budget(parts: Sequence[ModelContentPart]) -> None:
    media_parts = tuple(part for part in parts if isinstance(part, _MediaPart))
    if media_parts:
        if len(media_parts) > min(part._limits.max_media_parts for part in media_parts):
            raise AgentDefinitionError("Model message has too many media parts")
        total_inline_bytes = sum(
            0 if part.size is None else part.size for part in media_parts
        )
        if total_inline_bytes > min(
            part._limits.max_inline_bytes for part in media_parts
        ):
            raise AgentDefinitionError(
                "Model message exceeds its total inline byte limit"
            )


def model_content_text(content: ModelContent) -> str:
    """Return only ordered textual segments without inventing media descriptions."""
    if isinstance(content, str):
        return content
    return "".join(
        part.text for part in model_content_parts(content) if isinstance(part, TextPart)
    )


def model_content_size(content: ModelContent) -> int:
    """Return UTF-8 text plus known inline media bytes; remote size is unknown."""
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    size = 0
    for part in model_content_parts(content):
        if isinstance(part, TextPart):
            size += len(part.text.encode("utf-8"))
        elif part.size is not None:
            size += part.size
    return size


def serialize_model_content(content: ModelContent) -> JsonValue:
    """Serialize model content to a deterministic JSON-safe checkpoint shape."""
    if isinstance(content, str):
        return content
    serialized: list[JsonObject] = []
    for part in model_content_parts(content):
        if isinstance(part, TextPart):
            serialized.append({"type": "text", "text": part.text})
            continue
        item: dict[str, JsonValue] = {
            "type": part._KIND,
            "media_type": part.media_type,
            "limits": {
                "max_inline_bytes": part._limits.max_inline_bytes,
                "max_media_parts": part._limits.max_media_parts,
                "allowed_uri_schemes": tuple(sorted(part._limits.allowed_uri_schemes)),
                "allowed_uri_hosts": (
                    None
                    if part._limits.allowed_uri_hosts is None
                    else tuple(sorted(part._limits.allowed_uri_hosts))
                ),
            },
        }
        if part.uri is not None:
            item["uri"] = part.uri
        else:
            if part.data is None:
                raise AgentDefinitionError("Inline model media bytes are missing")
            item["data"] = b64encode(part.data).decode("ascii")
        if part.source is not None:
            item["source"] = part.source
        if part.content_digest is not None:
            item["content_digest"] = part.content_digest
        if isinstance(part, DocumentPart) and part.filename is not None:
            item["filename"] = part.filename
        serialized.append(item)
    return tuple(serialized)


def restore_model_content(value: object) -> str | tuple[ModelContentPart, ...]:
    """Restore trusted types from an untrusted JSON checkpoint boundary."""
    if isinstance(value, str):
        return value
    if not isinstance(value, Sequence) or isinstance(value, bytes | bytearray):
        raise AgentDefinitionError("Serialized model content must be text or an array")
    restored: list[ModelContentPart] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise AgentDefinitionError(
                "Serialized model content part must be an object"
            )
        kind = item.get("type")
        if kind == "text":
            if set(item) != {"type", "text"} or not isinstance(item.get("text"), str):
                raise AgentDefinitionError("Serialized text content part is invalid")
            restored.append(TextPart(item["text"]))
            continue
        media_class = _media_class(kind)
        allowed_keys = {
            "type",
            "media_type",
            "uri",
            "data",
            "source",
            "content_digest",
            "filename",
            "limits",
        }
        if not set(item) <= allowed_keys:
            raise AgentDefinitionError(
                "Serialized media content part has unknown fields"
            )
        media_type = item.get("media_type")
        source = item.get("source")
        content_digest = item.get("content_digest")
        filename = item.get("filename")
        raw_limits = item.get("limits")
        if not isinstance(media_type, str):
            raise AgentDefinitionError("Serialized media MIME type is invalid")
        if source is not None and not isinstance(source, str):
            raise AgentDefinitionError("Serialized media source provenance is invalid")
        if content_digest is not None and not isinstance(content_digest, str):
            raise AgentDefinitionError("Serialized media digest provenance is invalid")
        if filename is not None and not isinstance(filename, str):
            raise AgentDefinitionError("Serialized document filename is invalid")
        if media_class is not DocumentPart and filename is not None:
            raise AgentDefinitionError("Serialized filename requires document content")
        limits = _restore_limits(raw_limits)
        uri = item.get("uri")
        encoded = item.get("data")
        if uri is not None:
            if not isinstance(uri, str) or encoded is not None:
                raise AgentDefinitionError("Serialized media source is ambiguous")
            if media_class is DocumentPart:
                restored.append(
                    DocumentPart.from_uri(
                        uri,
                        media_type=media_type,
                        filename=filename,
                        source=source,
                        content_digest=content_digest,
                        limits=limits,
                    )
                )
            else:
                restored.append(
                    media_class.from_uri(
                        uri,
                        media_type=media_type,
                        source=source,
                        content_digest=content_digest,
                        limits=limits,
                    )
                )
            continue
        if not isinstance(encoded, str):
            raise AgentDefinitionError("Serialized inline media data is invalid")
        max_encoded_size = ((limits.max_inline_bytes + 2) // 3) * 4
        if len(encoded) > max_encoded_size:
            raise AgentDefinitionError(
                "Serialized inline media exceeds its encoded byte limit"
            )
        try:
            data = b64decode(encoded, validate=True)
        except (Base64Error, ValueError) as error:
            raise AgentDefinitionError(
                "Serialized inline media base64 is invalid"
            ) from error
        if media_class is DocumentPart:
            restored.append(
                DocumentPart.from_bytes(
                    data,
                    media_type=media_type,
                    filename=filename,
                    source=source,
                    content_digest=content_digest,
                    limits=limits,
                )
            )
        else:
            restored.append(
                media_class.from_bytes(
                    data,
                    media_type=media_type,
                    source=source,
                    content_digest=content_digest,
                    limits=limits,
                )
            )
    return tuple(model_content_parts(tuple(restored)))


def _media_class(
    kind: object,
) -> type[ImagePart] | type[AudioPart] | type[VideoPart] | type[DocumentPart]:
    classes: dict[
        str,
        type[ImagePart] | type[AudioPart] | type[VideoPart] | type[DocumentPart],
    ] = {
        "image": ImagePart,
        "audio": AudioPart,
        "video": VideoPart,
        "document": DocumentPart,
    }
    if not isinstance(kind, str) or kind not in classes:
        raise AgentDefinitionError("Serialized media content type is invalid")
    return classes[kind]


def _restore_limits(value: object) -> MediaSafetyLimits:
    if not isinstance(value, Mapping) or set(value) != {
        "max_inline_bytes",
        "max_media_parts",
        "allowed_uri_schemes",
        "allowed_uri_hosts",
    }:
        raise AgentDefinitionError("Serialized media safety limits are invalid")
    max_inline_bytes = value.get("max_inline_bytes")
    max_media_parts = value.get("max_media_parts")
    raw_schemes = value.get("allowed_uri_schemes")
    raw_hosts = value.get("allowed_uri_hosts")
    if (
        isinstance(max_inline_bytes, bool)
        or not isinstance(max_inline_bytes, int)
        or isinstance(max_media_parts, bool)
        or not isinstance(max_media_parts, int)
        or not isinstance(raw_schemes, Sequence)
        or isinstance(raw_schemes, str | bytes | bytearray)
        or any(not isinstance(scheme, str) for scheme in raw_schemes)
        or (
            raw_hosts is not None
            and (
                not isinstance(raw_hosts, Sequence)
                or isinstance(raw_hosts, str | bytes | bytearray)
                or any(not isinstance(host, str) for host in raw_hosts)
            )
        )
    ):
        raise AgentDefinitionError("Serialized media safety limits are invalid")
    return MediaSafetyLimits(
        max_inline_bytes=max_inline_bytes,
        max_media_parts=max_media_parts,
        allowed_uri_schemes=frozenset(raw_schemes),
        allowed_uri_hosts=(None if raw_hosts is None else frozenset(raw_hosts)),
    )
