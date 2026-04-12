"""Security-related error classes.

Provides specialized exception classes for cryptography, key management,
and JWT processing errors.
"""

from typing import final

from spakky.core.common.error import AbstractSpakkyFrameworkError


@final
class DecryptionFailedError(AbstractSpakkyFrameworkError):
    """Raised when decryption fails due to invalid key or corrupted data."""

    message = "Decryption failed. Check secret key or cipher message."


@final
class KeySizeError(AbstractSpakkyFrameworkError):
    """Raised when a cryptographic key has an invalid size."""

    message = "Invalid key size."


@final
class PrivateKeyRequiredError(AbstractSpakkyFrameworkError):
    """Raised when a private key is required but not provided."""

    message = "Private key is required to decrypt or sign."


@final
class CannotImportAsymmetricKeyError(AbstractSpakkyFrameworkError):
    """Raised when an asymmetric key cannot be imported."""

    message = "Cannot import asymmetric key."


@final
class InvalidJWTFormatError(AbstractSpakkyFrameworkError):
    """Raised when a JWT token has an invalid format."""

    message = "parameter 'token' is not a valid data (which has 3 separated values.)"


@final
class JWTDecodingError(AbstractSpakkyFrameworkError):
    """Raised when JWT token decoding fails."""

    message = "parameter 'token' is not a valid data (json decoding error.)"


@final
class JWTProcessingError(AbstractSpakkyFrameworkError):
    """Raised when JWT token processing encounters an error."""

    message = "Something went wrong to process JWT token"


@final
class InvalidKeyConstructorCallError(AbstractSpakkyFrameworkError):
    """Raised when Key constructor is called without valid arguments."""

    message = "Invalid call of constructor Key()."


@final
class PasswordRequiredError(AbstractSpakkyFrameworkError):
    """Raised when password parameter is required but not provided."""

    message = "parameter 'password' cannot be None"


@final
class AsymmetricKeyRequiredError(AbstractSpakkyFrameworkError):
    """Raised when key or size parameter is required but not provided."""

    message = "'key' or 'size' must be specified"
