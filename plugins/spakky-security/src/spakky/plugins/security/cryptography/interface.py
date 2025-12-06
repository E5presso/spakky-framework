"""Cryptography protocol interfaces.

Defines protocol interfaces for encryption/decryption and signing/verification
operations used by cryptographic implementations.
"""

from abc import ABC, abstractmethod

from spakky.plugins.security.hash import HashType


class ICryptor(ABC):
    """Protocol for encryption and decryption operations."""

    url_safe: bool

    @abstractmethod
    def encrypt(self, message: str) -> str: ...

    @abstractmethod
    def decrypt(self, cipher: str) -> str: ...


class ISigner(ABC):
    """Protocol for digital signature operations."""

    url_safe: bool

    @abstractmethod
    def sign(self, message: str, hash_type: HashType = HashType.SHA256) -> str: ...

    @abstractmethod
    def verify(
        self, message: str, signature: str, hash_type: HashType = HashType.SHA256
    ) -> bool: ...
