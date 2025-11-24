"""Cryptographic hash utilities.

Provides utilities for computing cryptographic hashes using various algorithms
including MD5, SHA1, SHA224, SHA256, SHA384, and SHA512.
"""

from enum import Enum
from io import BufferedReader
from typing import final

from Crypto.Hash import MD5, SHA1, SHA224, SHA256, SHA384, SHA512

from spakky_security.encoding import Base64Encoder


@final
class HashType(str, Enum):
    """Supported cryptographic hash algorithms."""

    MD5 = "MD5"
    SHA1 = "SHA1"
    SHA224 = "SHA224"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"


@final
class Hash:
    """Cryptographic hash computation utility.

    Computes cryptographic hashes of strings or file streams using various
    hash algorithms. Supports multiple output formats including hex, Base64,
    and binary.
    """

    __hash_type: HashType

    def __init__(
        self, data: str | BufferedReader, hash_type: HashType = HashType.SHA256
    ) -> None:
        """Initialize a hash computation.

        Args:
            data: The data to hash (string or file stream).
            hash_type: The hash algorithm to use.
        """
        self.__hash_type = hash_type
        match self.__hash_type:
            case HashType.MD5:
                self.__hash = MD5.new()
            case HashType.SHA1:
                self.__hash = SHA1.new()  # pyrefly: ignore
            case HashType.SHA224:
                self.__hash = SHA224.new()  # pyrefly: ignore
            case HashType.SHA256:
                self.__hash = SHA256.new()  # pyrefly: ignore
            case HashType.SHA384:
                self.__hash = SHA384.new()  # pyrefly: ignore
            case HashType.SHA512:  # pragma: no cover
                self.__hash = SHA512.new()  # pyrefly: ignore
        if isinstance(data, str):
            self.__hash.update(data.encode("UTF-8"))
        if isinstance(data, BufferedReader):
            while True:
                buffer: bytes = data.read(65536)
                if not any(buffer):
                    break
                self.__hash.update(buffer)

    @property
    def hex(self) -> str:
        """Get hash as uppercase hexadecimal string."""
        return self.__hash.hexdigest().upper()

    @property
    def b64(self) -> str:
        """Get hash as Base64-encoded string."""
        return Base64Encoder.from_bytes(self.__hash.digest())

    @property
    def b64_urlsafe(self) -> str:
        """Get hash as URL-safe Base64-encoded string."""
        return Base64Encoder.from_bytes(self.__hash.digest(), url_safe=True)

    @property
    def binary(self) -> bytes:
        """Get hash as binary data."""
        return self.__hash.digest()

    @property
    def oid(self) -> str:
        """Get the OID (Object Identifier) of the hash algorithm."""
        return self.__hash.oid

    def digest(self) -> bytes:
        """Compute and return the hash digest as binary data.

        Returns:
            The hash digest as bytes.
        """
        return self.__hash.digest()
