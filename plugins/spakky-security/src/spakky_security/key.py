"""Cryptographic key management utilities.

Provides utilities for generating, storing, and converting cryptographic keys
in various formats including binary, Base64, and hexadecimal.
"""

import secrets
from typing import Any, final, overload

from spakky_security.encoding import Base64Encoder


@final
class Key:
    """Cryptographic key wrapper with format conversion utilities.

    Supports creating keys from random generation, binary data, or Base64
    encoding. Provides properties for converting keys to different formats.
    """

    __binary: bytes

    @overload
    def __init__(self, *, size: int) -> None: ...

    @overload
    def __init__(self, *, binary: bytes) -> None: ...

    @overload
    def __init__(self, *, base64: str, url_safe: bool = False) -> None: ...

    def __init__(
        self,
        size: int | None = None,
        binary: bytes | None = None,
        base64: str | None = None,
        url_safe: bool = False,
    ) -> None:
        """Initialize a cryptographic key.

        Args:
            size: Generate a random key of specified byte size.
            binary: Create key from binary data.
            base64: Create key from Base64-encoded string.
            url_safe: Use URL-safe Base64 decoding when base64 is provided.

        Raises:
            ValueError: If no valid initialization method is provided.
        """
        if size is not None:
            self.__binary = secrets.token_bytes(size)
            return
        if binary is not None:
            self.__binary = binary
            return
        if base64 is not None:
            self.__binary = Base64Encoder.get_bytes(base64, url_safe=url_safe)
            return
        raise ValueError("Invalid call of constructor Key().")

    @property
    def binary(self) -> bytes:
        """Get the key as binary data."""
        return self.__binary

    @property
    def length(self) -> int:
        """Get the key length in bytes."""
        return len(self.__binary)

    @property
    def b64(self) -> str:
        """Get the key as Base64-encoded string."""
        return Base64Encoder.from_bytes(self.__binary)

    @property
    def b64_urlsafe(self) -> str:
        """Get the key as URL-safe Base64-encoded string."""
        return Base64Encoder.from_bytes(self.__binary, True)

    @property
    def hex(self) -> str:
        """Get the key as uppercase hexadecimal string."""
        return self.__binary.hex().upper()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Key):
            raise TypeError
        return self.binary == other.binary

    def __ne__(self, other: Any) -> bool:
        return not self == other
