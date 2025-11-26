"""JSON Web Token (JWT) utilities.

Provides utilities for creating, signing, verifying, and parsing JWT tokens
with support for various HMAC algorithms and standard JWT claims.
"""

import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Sequence, final
from uuid import UUID, uuid4

from spakky_security.encoding import Base64Encoder
from spakky_security.error import (
    InvalidJWTFormatError,
    JWTDecodingError,
    JWTProcessingError,
)
from spakky_security.hmac_signer import HMAC, HMACType
from spakky_security.key import Key

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


@final
class JWT:
    """JSON Web Token (JWT) implementation.

    Supports creating, signing, verifying, and parsing JWT tokens with
    standard claims (jti, iat, exp, etc.) and custom payload data.
    """

    __header: dict[str, Any]
    __payload: dict[str, Any]
    __key: Key | None
    __signature: str | None
    __is_signed: bool = False

    @property
    def hash_type(self) -> HMACType:
        """Get the HMAC algorithm used for signing."""
        return HMACType(self.__header["alg"])

    @property
    def id(self) -> UUID | None:
        """Get the JWT ID (jti claim) as a UUID."""
        jti: str | None = self.__payload.get("jti")
        return UUID(jti) if jti is not None else None

    @property
    def header(self) -> dict[str, Any]:
        """Get a copy of the JWT header dictionary."""
        return deepcopy(self.__header)

    @property
    def payload(self) -> dict[str, Any]:
        """Get a copy of the JWT payload dictionary."""
        return deepcopy(self.__payload)

    @property
    def signature(self) -> str | None:
        """Get the JWT signature string."""
        return self.__signature

    @property
    def issued_at(self) -> datetime | None:
        """Get the issued-at time (iat claim) as a datetime."""
        iat: int | None = self.__payload.get("iat")
        return self.__convert_datetime(iat) if iat is not None else None

    @property
    def updated_at(self) -> datetime | None:
        """Get the updated-at time (updated_at claim) as a datetime."""
        updated_at: int | None = self.__payload.get("updated_at")
        return self.__convert_datetime(updated_at) if updated_at is not None else None

    @property
    def last_authorized(self) -> datetime | None:
        """Get the last authorization time (auth_time claim) as a datetime."""
        auth_time: int | None = self.__payload.get("auth_time")
        return self.__convert_datetime(auth_time) if auth_time is not None else None

    @property
    def is_expired(self) -> bool:
        """Check if the JWT has expired based on the exp claim."""
        exp: int | None = self.__payload.get("exp")
        return (
            self.__convert_datetime(exp) < datetime.now() if exp is not None else False
        )

    @property
    def is_signed(self) -> bool:
        """Check if the JWT has been signed."""
        return self.__is_signed

    def __init__(self, token: str | None = None) -> None:
        """Initialize JWT.

        Args:
            token: Existing JWT token string to parse, or None to create new.

        Raises:
            InvalidJWTFormatError: If token format is invalid.
            JWTDecodingError: If token cannot be decoded.
        """
        if token is not None:
            parts: Sequence[str] = token.split(".")
            if len(parts) != 3:
                raise InvalidJWTFormatError
            header, body, signature = parts
            try:
                self.__header = json.loads(
                    Base64Encoder.decode(b64=header, url_safe=True)
                )
                self.__payload = json.loads(
                    Base64Encoder.decode(b64=body, url_safe=True)
                )
            except Exception as e:
                raise JWTDecodingError from e
            self.__signature = signature
            self.__is_signed = False
        else:
            current_time: datetime = datetime.now()
            self.__header = {
                "typ": "JWT",
                "alg": HMACType.HS256,
            }
            self.__payload = {
                "jti": str(uuid4()),
                "iat": self.__convert_unixtime(current_time),
            }
            self.__signature = None

    def __sign(self) -> None:
        header: str = Base64Encoder.encode(
            utf8=json.dumps(self.__header), url_safe=True
        )
        payload: str = Base64Encoder.encode(
            utf8=json.dumps(self.__payload), url_safe=True
        )
        data_to_sign: str = f"{header}.{payload}"
        sign_algorithm: HMACType | None = self.__header.get("alg")
        if self.__key is None:  # pragma: no cover
            raise JWTProcessingError("sign key cannot be None")
        if sign_algorithm is None:  # pragma: no cover
            raise JWTProcessingError("field named 'alg' does not exists in header")
        self.__signature = HMAC.sign_text(
            self.__key,
            sign_algorithm,
            data_to_sign,
            True,
        )
        self.__is_signed = True

    def __convert_datetime(self, unix_time: int) -> datetime:
        return datetime.fromtimestamp(float(unix_time))

    def __convert_unixtime(self, date_time: datetime) -> int:
        return int(date_time.timestamp())

    def set_header(self, **kwargs: Any) -> Self:
        """Set header fields.

        Args:
            **kwargs: Header fields to set.

        Returns:
            Self for method chaining.
        """
        for key, value in kwargs.items():
            self.__header[key] = value
        # Mutating header claims invalidates the previous signature, so we
        # immediately re-sign to keep the token cryptographically consistent.
        if self.__is_signed:
            self.__sign()
        return self

    def set_payload(self, **kwargs: Any) -> Self:
        """Set payload fields.

        Args:
            **kwargs: Payload fields to set.

        Returns:
            Self for method chaining.
        """
        for key, value in kwargs.items():
            self.__payload[key] = value
        # Payload updates must refresh the signature as well, otherwise
        # consumers would observe stale token integrity data.
        if self.__is_signed:
            self.__sign()
        return self

    def set_hash_type(self, hash_type: HMACType) -> Self:
        """Set the HMAC hash algorithm.

        Args:
            hash_type: HMAC algorithm to use for signing.

        Returns:
            Self for method chaining.
        """
        self.__header["alg"] = hash_type
        # Changing the algorithm affects the signing key usage, so rebuild the
        # signature immediately when the token was already signed before.
        if self.__is_signed:
            self.__sign()
        return self

    def set_expiration(self, expire_after: timedelta) -> Self:
        """Set token expiration time.

        Args:
            expire_after: Time duration until token expires.

        Returns:
            Self for method chaining.

        Raises:
            JWTProcessingError: If 'iat' claim is missing.
        """
        iat_value: int | None = self.__payload.get("iat")
        if iat_value is None:
            raise JWTProcessingError("field named 'iat' does not exists in payload")
        iat: datetime = self.__convert_datetime(iat_value)
        exp: int = self.__convert_unixtime(iat + expire_after)
        self.__payload["exp"] = exp
        self.__payload["updated_at"] = self.__convert_unixtime(datetime.now())
        # Expiration bumps happen on long-lived tokens; re-signing keeps the
        # issued token aligned with the new expiry metadata.
        if self.__is_signed:
            self.__sign()
        return self

    def refresh(self, expire_after: timedelta) -> Self:
        """Refresh token with new expiration time.

        Args:
            expire_after: Time duration until token expires.

        Returns:
            Self for method chaining.
        """
        current_time: datetime = datetime.now()
        self.__payload["exp"] = self.__convert_unixtime(current_time + expire_after)
        self.__payload["updated_at"] = self.__convert_unixtime(current_time)
        # Refresh logic is invoked on already issued tokens, so always renew
        # the signature alongside the refreshed timestamps.
        if self.__is_signed:
            self.__sign()
        return self

    def sign(self, key: Key) -> Self:
        """Sign the JWT with a key.

        Args:
            key: Cryptographic key to use for signing.

        Returns:
            Self for method chaining.
        """
        self.__key = key
        self.__sign()
        return self

    def verify(self, key: Key) -> bool:
        """Verify JWT signature.

        Args:
            key: Cryptographic key to use for verification.

        Returns:
            True if signature is valid, False otherwise.

        Raises:
            JWTProcessingError: If signature or algorithm is missing.
        """
        self.__key = key
        header: str = Base64Encoder.encode(
            utf8=json.dumps(self.__header), url_safe=True
        )
        payload: str = Base64Encoder.encode(
            utf8=json.dumps(self.__payload), url_safe=True
        )
        content: str = f"{header}.{payload}"
        sign_algorithm: HMACType | None = self.__header.get("alg")
        if self.__signature is None:
            raise JWTProcessingError("signature cannot be None")
        if sign_algorithm is None:  # pragma: no cover
            raise JWTProcessingError("field named 'alg' does not exists in header")
        verification_result: bool = HMAC.verify(
            key=self.__key,
            hmac_type=sign_algorithm,
            content=content,
            signature=self.__signature,
            url_safe=True,
        )
        if verification_result:
            self.__payload["auth_time"] = self.__convert_unixtime(datetime.now())
            self.__is_signed = verification_result
        return verification_result

    def export(self) -> str:
        """Export JWT as a token string.

        Returns:
            JWT token string in format "header.payload.signature".

        Raises:
            JWTProcessingError: If token is not signed.
        """
        if self.__is_signed:
            header: str = Base64Encoder.encode(
                utf8=json.dumps(self.__header), url_safe=True
            )
            payload: str = Base64Encoder.encode(
                json.dumps(self.__payload), url_safe=True
            )
            return f"{header}.{payload}.{self.__signature}"
        raise JWTProcessingError("Token must be signed")
