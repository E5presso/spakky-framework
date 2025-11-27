"""AES encryption and decryption utilities.

Provides AES-CBC mode encryption/decryption with automatic padding
and IV generation using 256-bit keys.
"""

from typing import ClassVar, final

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from spakky_security.cryptography.interface import ICryptor
from spakky_security.encoding import Base64Encoder
from spakky_security.error import DecryptionFailedError, KeySizeError
from spakky_security.key import Key


@final
class Aes(ICryptor):
    """AES-CBC encryption/decryption implementation.

    Uses 256-bit keys (32 bytes) with automatic PKCS7 padding and
    random IV generation for each encryption operation.
    """

    KEY_SIZE: ClassVar[int] = 32
    url_safe: bool
    __key: Key

    def __init__(self, key: Key, url_safe: bool = False) -> None:
        """Initialize AES encryptor.

        Args:
            key: 256-bit (32-byte) encryption key.
            url_safe: Use URL-safe Base64 encoding for cipher text.

        Raises:
            KeySizeError: If key is not 32 bytes.
        """
        if key.length != self.KEY_SIZE:
            raise KeySizeError
        self.url_safe = url_safe
        self.__key = key

    def encrypt(self, message: str) -> str:
        """Encrypt a message using AES-CBC.

        Args:
            message: Plain text message to encrypt.

        Returns:
            Encrypted cipher text in format "iv:cipher" (Base64 encoded).
        """
        plain_bytes: bytes = pad(message.encode(), AES.block_size)
        iv: Key = Key(size=16)
        cryptor = AES.new(  # pyrefly: ignore  # type: ignore
            key=self.__key.binary,
            mode=AES.MODE_CBC,
            iv=iv.binary,
        )
        cipher_bytes: bytes = cryptor.encrypt(plain_bytes)
        return "{iv}:{cipher}".format(
            iv=iv.b64_urlsafe if self.url_safe else iv.b64,
            cipher=Base64Encoder.from_bytes(cipher_bytes, self.url_safe),
        )

    def decrypt(self, cipher: str) -> str:
        """Decrypt a cipher text using AES-CBC.

        Args:
            cipher: Cipher text in format "iv:cipher" (Base64 encoded).

        Returns:
            Decrypted plain text message.

        Raises:
            DecryptionFailedError: If decryption fails.
        """
        try:
            [iv, cipher] = cipher.split(":")
            iv_bytes: bytes = Base64Encoder.get_bytes(iv, self.url_safe)
            cipher_bytes: bytes = Base64Encoder.get_bytes(cipher, self.url_safe)
            cryptor = AES.new(  # pyrefly: ignore  # type: ignore
                key=self.__key.binary,
                mode=AES.MODE_CBC,
                iv=iv_bytes,
            )
            plain_bytes: bytes = cryptor.decrypt(cipher_bytes)
            return unpad(plain_bytes, AES.block_size).decode()
        except Exception as e:
            raise DecryptionFailedError from e
