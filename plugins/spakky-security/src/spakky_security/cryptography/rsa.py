"""RSA encryption, decryption, and signing utilities.

Provides RSA asymmetric cryptography operations including key generation,
encryption/decryption with PKCS1_OAEP, and signing/verification with PKCS1_v1_5.
"""

from typing import ClassVar, final, overload

from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.PublicKey.RSA import RsaKey
from Crypto.Signature import PKCS1_v1_5

from spakky_security.cryptography.interface import ICryptor, ISigner
from spakky_security.encoding import Base64Encoder
from spakky_security.error import (
    CannotImportAsymmetricKeyError,
    DecryptionFailedError,
    KeySizeError,
    PrivateKeyRequiredError,
)
from spakky_security.hash import Hash, HashType
from spakky_security.key import Key


@final
class AsymmetricKey:
    """RSA asymmetric key pair.

    Manages RSA public/private key pairs with support for key generation,
    import/export, and passphrase protection. Supports 1024, 2048, 4096,
    and 8192-bit keys.
    """

    KEY_SIZES: ClassVar[list[int]] = [1024, 2048, 4096, 8192]
    __key: RsaKey
    __private_key: Key | None = None
    __public_key: Key

    @property
    def is_private(self) -> bool:
        """Check if this key pair includes a private key."""
        return self.__private_key is not None

    @property
    def private_key(self) -> Key | None:
        """Get the private key, or None if this is a public key only."""
        return self.__private_key

    @property
    def public_key(self) -> Key:
        """Get the public key."""
        return self.__public_key

    @overload
    def __init__(self, *, key: str, passphrase: str | None = None) -> None: ...

    @overload
    def __init__(self, *, key: bytes, passphrase: str | None = None) -> None: ...

    @overload
    def __init__(self, *, size: int, passphrase: str | None = None) -> None: ...

    def __init__(
        self,
        key: str | bytes | None = None,
        size: int | None = None,
        passphrase: str | None = None,
    ) -> None:
        if key is None and size is None:  # pragma: no cover
            raise ValueError("'key' or 'size' must be specified")
        if key is not None:
            try:
                imported_key = RSA.import_key(key, passphrase)
                if (key_size := imported_key.size_in_bits()) not in self.KEY_SIZES:
                    raise KeySizeError(key_size * 8)
                self.__key = imported_key
            except (ValueError, IndexError, TypeError) as e:
                raise CannotImportAsymmetricKeyError from e
        if size is not None:
            if size not in self.KEY_SIZES:
                raise KeySizeError(size)
            self.__key = RSA.generate(size)
        if self.__key.has_private():
            self.__private_key = Key(
                binary=self.__key.export_key(passphrase=passphrase)
            )
        self.__public_key = Key(binary=self.__key.public_key().export_key())


@final
class Rsa(ICryptor, ISigner):
    """RSA encryption/decryption and signing/verification.

    Provides PKCS1_OAEP encryption/decryption and PKCS1_v1_5 signing/verification
    using RSA asymmetric keys. Encryption uses the public key, decryption and
    signing require the private key.
    """

    url_safe: bool
    __key: AsymmetricKey

    def __init__(self, key: AsymmetricKey, url_safe: bool = False) -> None:
        """Initialize RSA cryptor/signer.

        Args:
            key: RSA asymmetric key pair.
            url_safe: Use URL-safe Base64 encoding for cipher/signature.
        """
        self.url_safe = url_safe
        self.__key = key

    def encrypt(self, message: str) -> str:
        """Encrypt a message using RSA public key.

        Args:
            message: Plain text message to encrypt.

        Returns:
            Encrypted cipher text (Base64 encoded).
        """
        cryptor = PKCS1_OAEP.new(RSA.import_key(self.__key.public_key.binary))
        cipher_bytes: bytes = cryptor.encrypt(message.encode())
        return Base64Encoder.from_bytes(cipher_bytes, self.url_safe)

    def decrypt(self, cipher: str) -> str:
        """Decrypt a cipher text using RSA private key.

        Args:
            cipher: Cipher text to decrypt (Base64 encoded).

        Returns:
            Decrypted plain text message.

        Raises:
            PrivateKeyRequiredError: If key pair has no private key.
            DecryptionFailedError: If decryption fails.
        """
        if self.__key.private_key is None:
            raise PrivateKeyRequiredError
        try:
            cipher_bytes: bytes = Base64Encoder.get_bytes(cipher, self.url_safe)
            cryptor = PKCS1_OAEP.new(RSA.import_key(self.__key.private_key.binary))
            return cryptor.decrypt(cipher_bytes).decode()
        except Exception as e:
            raise DecryptionFailedError from e

    def sign(self, message: str, hash_type: HashType = HashType.SHA256) -> str:
        """Sign a message using RSA private key.

        Args:
            message: Message to sign.
            hash_type: Hash algorithm to use for signing.

        Returns:
            Digital signature (Base64 encoded).

        Raises:
            PrivateKeyRequiredError: If key pair has no private key.
        """
        if self.__key.private_key is None:
            raise PrivateKeyRequiredError
        signer = PKCS1_v1_5.new(RSA.import_key(self.__key.private_key.binary))
        signature_bytes: bytes = signer.sign(Hash(message, hash_type))
        return Base64Encoder.from_bytes(signature_bytes, self.url_safe)

    def verify(
        self, message: str, signature: str, hash_type: HashType = HashType.SHA256
    ) -> bool:
        """Verify a signature using RSA public key.

        Args:
            message: Original message that was signed.
            signature: Digital signature to verify (Base64 encoded).
            hash_type: Hash algorithm used for signing.

        Returns:
            True if signature is valid, False otherwise.
        """
        signature_bytes: bytes = Base64Encoder.get_bytes(signature, self.url_safe)
        signer = PKCS1_v1_5.new(RSA.import_key(self.__key.public_key.binary))
        return signer.verify(Hash(message, hash_type), signature_bytes)
