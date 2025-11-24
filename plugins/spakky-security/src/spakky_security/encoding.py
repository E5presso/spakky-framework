"""Base64 encoding and decoding utilities.

Provides utilities for encoding and decoding data in Base64 format with
support for URL-safe encoding and direct bytes conversion.
"""

import base64
from typing import final


@final
class Base64Encoder:
    """Utility class for Base64 encoding and decoding operations."""

    @staticmethod
    def encode(utf8: str, url_safe: bool = False) -> str:
        """Encode a UTF-8 string to Base64.

        Args:
            utf8: The string to encode.
            url_safe: Use URL-safe Base64 encoding without padding.

        Returns:
            The Base64-encoded string.
        """
        if url_safe:
            return (
                base64.urlsafe_b64encode(utf8.encode("UTF-8"))
                .decode("UTF-8")
                .rstrip("=")
            )
        return base64.b64encode(utf8.encode("UTF-8")).decode("UTF-8")

    @staticmethod
    def decode(b64: str, url_safe: bool = False) -> str:
        """Decode a Base64 string to UTF-8.

        Args:
            b64: The Base64-encoded string to decode.
            url_safe: Use URL-safe Base64 decoding with padding restoration.

        Returns:
            The decoded UTF-8 string.
        """
        if url_safe:
            return base64.urlsafe_b64decode(
                (b64 + ("=" * (4 - (len(b64) % 4)))).encode("UTF-8")
            ).decode("UTF-8")
        return base64.b64decode(b64.encode("UTF-8")).decode("UTF-8")

    @staticmethod
    def from_bytes(binary: bytes, url_safe: bool = False) -> str:
        """Encode binary data to Base64 string.

        Args:
            binary: The binary data to encode.
            url_safe: Use URL-safe Base64 encoding without padding.

        Returns:
            The Base64-encoded string.
        """
        if url_safe:
            return base64.urlsafe_b64encode(binary).decode("UTF-8").rstrip("=")
        return base64.b64encode(binary).decode("UTF-8")

    @staticmethod
    def get_bytes(b64: str, url_safe: bool = False) -> bytes:
        """Decode a Base64 string to binary data.

        Args:
            b64: The Base64-encoded string to decode.
            url_safe: Use URL-safe Base64 decoding with padding restoration.

        Returns:
            The decoded binary data.
        """
        if url_safe:
            return base64.urlsafe_b64decode(
                (b64 + ("=" * (4 - (len(b64) % 4)))).encode("UTF-8")
            )
        return base64.b64decode(b64.encode("UTF-8"))
