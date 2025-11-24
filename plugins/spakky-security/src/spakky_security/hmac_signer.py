"""HMAC signing and verification utilities.

Provides utilities for creating and verifying HMAC signatures using various
hash algorithms (SHA-224, SHA-256, SHA-384, SHA-512).
"""

import hashlib
import hmac
from enum import Enum
from typing import Any, Callable, final

from spakky_security.encoding import Base64Encoder
from spakky_security.key import Key


@final
class HMACType(str, Enum):
    """Supported HMAC hash algorithms."""

    HS224 = "HS224"
    HS256 = "HS256"
    HS384 = "HS384"
    HS512 = "HS512"


@final
class HMAC:
    """HMAC signing and verification utility.

    Provides static methods for creating and verifying HMAC signatures
    using various hash algorithms.
    """

    @staticmethod
    def sign_text(
        key: Key,
        hmac_type: HMACType,
        content: str,
        url_safe: bool = False,
    ) -> str:
        """Sign text content with HMAC.

        Args:
            key: The cryptographic key to use for signing.
            hmac_type: The HMAC hash algorithm to use.
            content: The text content to sign.
            url_safe: Use URL-safe Base64 encoding for the signature.

        Returns:
            The HMAC signature as a Base64-encoded string.
        """
        key_bytes: bytes = key.binary
        hash_function: Callable[..., Any]
        match hmac_type:
            case HMACType.HS224:
                hash_function = hashlib.sha224
            case HMACType.HS256:
                hash_function = hashlib.sha256
            case HMACType.HS384:
                hash_function = hashlib.sha384
            case HMACType.HS512:
                hash_function = hashlib.sha512  # pragma: no cover
        return Base64Encoder.from_bytes(
            hmac.new(
                key_bytes,
                content.encode("UTF-8"),
                hash_function,  # pyrefly: ignore
            ).digest(),
            url_safe,
        )

    @staticmethod
    def verify(
        key: Key,
        hmac_type: HMACType,
        content: str,
        signature: str,
        url_safe: bool = False,
    ) -> bool:
        """Verify HMAC signature of text content.

        Args:
            key: The cryptographic key used for verification.
            hmac_type: The HMAC hash algorithm to use.
            content: The text content to verify.
            signature: The expected HMAC signature as a Base64 string.
            url_safe: Whether the signature uses URL-safe Base64 encoding.

        Returns:
            True if the signature is valid, False otherwise.
        """
        key_bytes: bytes = key.binary
        hash_function: Callable[..., Any]
        match hmac_type:
            case HMACType.HS224:
                hash_function = hashlib.sha224
            case HMACType.HS256:
                hash_function = hashlib.sha256
            case HMACType.HS384:
                hash_function = hashlib.sha384
            case HMACType.HS512:
                hash_function = hashlib.sha512  # pragma: no cover
        return (
            Base64Encoder.from_bytes(
                hmac.new(
                    key_bytes,
                    content.encode("UTF-8"),
                    hash_function,  # pyrefly: ignore
                ).digest(),
                url_safe,
            )
            == signature
        )
