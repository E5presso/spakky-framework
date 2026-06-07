"""Cryptography provider plugin public API."""

from spakky.core.application.plugin import Plugin
from spakky.plugins.cryptography.auth_provider import (
    AuthContextSnapshotVerificationResult,
    CryptographyAuthProvider,
    CryptographyAuthProviderConfig,
)
from spakky.plugins.cryptography.cryptography.aes import Aes
from spakky.plugins.cryptography.cryptography.gcm import Gcm
from spakky.plugins.cryptography.cryptography.interface import ICryptor, ISigner
from spakky.plugins.cryptography.cryptography.rsa import AsymmetricKey, Rsa
from spakky.plugins.cryptography.encoding import Base64Encoder
from spakky.plugins.cryptography.hash import Hash, HashType
from spakky.plugins.cryptography.hmac_signer import HMAC, HMACType
from spakky.plugins.cryptography.key import Key
from spakky.plugins.cryptography.password.argon2 import Argon2PasswordEncoder
from spakky.plugins.cryptography.password.bcrypt import BcryptPasswordEncoder
from spakky.plugins.cryptography.password.interface import IPasswordEncoder
from spakky.plugins.cryptography.password.pbkdf2 import Pbkdf2PasswordEncoder
from spakky.plugins.cryptography.password.scrypt import ScryptPasswordEncoder

PLUGIN_NAME = Plugin(name="spakky-cryptography")

__all__ = [
    "PLUGIN_NAME",
    "Aes",
    "Argon2PasswordEncoder",
    "AsymmetricKey",
    "AuthContextSnapshotVerificationResult",
    "Base64Encoder",
    "BcryptPasswordEncoder",
    "CryptographyAuthProvider",
    "CryptographyAuthProviderConfig",
    "Gcm",
    "HMAC",
    "HMACType",
    "Hash",
    "HashType",
    "ICryptor",
    "IPasswordEncoder",
    "ISigner",
    "Key",
    "Pbkdf2PasswordEncoder",
    "Rsa",
    "ScryptPasswordEncoder",
]
