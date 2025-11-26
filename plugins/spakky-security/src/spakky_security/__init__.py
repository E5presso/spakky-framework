"""Security utilities plugin for Spakky framework.

This plugin provides comprehensive security utilities with:
- Password hashing (Argon2, bcrypt, scrypt, PBKDF2)
- Symmetric encryption (AES-GCM, ChaCha20-Poly1305)
- Asymmetric encryption (RSA, Ed25519)
- JWT token generation and validation
- HMAC signing and verification
- Secure key generation and management

Example:
    >>> from spakky_security.password import PasswordEncoder
    >>> from spakky_security.jwt import JWTService
    >>>
    >>> encoder = PasswordEncoder()
    >>> hashed = encoder.encode("password123")
    >>> is_valid = encoder.verify("password123", hashed)
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-security")
"""Plugin identifier for the security utilities."""
