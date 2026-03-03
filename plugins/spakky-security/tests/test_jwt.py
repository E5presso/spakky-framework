from datetime import timedelta

import pytest

from spakky.plugins.security.error import (
    InvalidJWTFormatError,
    JWTDecodingError,
    JWTProcessingError,
)
from spakky.plugins.security.hmac_signer import HMACType
from spakky.plugins.security.jwt import JWT
from spakky.plugins.security.key import Key


def test_jwt_create() -> None:
    """JWT 기본 생성 시 헤더와 페이로드가 올바르게 초기화되는지 검증한다."""
    jwt: JWT = JWT()
    assert jwt.header["typ"] == "JWT"
    assert jwt.header["alg"] == HMACType.HS256
    assert jwt.payload != {}
    assert jwt.id is not None
    assert jwt.issued_at is not None
    assert jwt.updated_at is None
    assert jwt.last_authorized is None
    assert not jwt.is_expired
    assert not jwt.is_signed
    assert jwt.signature is None


def test_jwt_from_string() -> None:
    """토큰 문자열로부터 JWT를 생성하면 페이로드와 서명이 올바르게 파싱되는지 검증한다."""
    jwt: JWT = JWT(
        token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    assert jwt.header["typ"] == "JWT"
    assert jwt.header["alg"] == HMACType.HS256
    assert jwt.payload == {"sub": "1234567890", "name": "John Doe", "iat": 1516239022}
    assert jwt.id is None
    assert jwt.issued_at is not None
    assert jwt.updated_at is None
    assert jwt.last_authorized is None
    assert not jwt.is_expired
    assert jwt.signature == "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"


def test_jwt_from_string_expect_invalid_jwt_format_error() -> None:
    """잘못된 JWT 형식의 토큰을 파싱하면 InvalidJWTFormatError가 발생하는지 검증한다."""
    with pytest.raises(InvalidJWTFormatError):
        JWT(
            token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQSflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )


def test_jwt_from_string_expect_jwt_decoding_error() -> None:
    """디코딩할 수 없는 JWT 토큰을 파싱하면 JWTDecodingError가 발생하는지 검증한다."""
    with pytest.raises(JWTDecodingError):
        JWT(
            token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyf.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )


def test_jwt_set_header() -> None:
    """JWT 헤더에 새 필드를 추가하면 올바르게 설정되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.set_header(meta="META")

    assert jwt.header["meta"] == "META"


def test_jwt_set_header_signed() -> None:
    """서명된 JWT의 헤더를 수정하면 올바르게 설정되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.sign(Key(size=32))
    jwt.set_header(meta="META")

    assert jwt.header["meta"] == "META"


def test_jwt_set_payload() -> None:
    """JWT 페이로드에 새 필드를 추가하면 올바르게 설정되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.set_payload(age=29)

    assert jwt.payload["age"] == 29


def test_jwt_set_payload_signed() -> None:
    """서명된 JWT의 페이로드를 수정하면 올바르게 설정되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.sign(Key(size=32))
    jwt.set_payload(age=29)

    assert jwt.payload["age"] == 29


def test_jwt_set_hash_type() -> None:
    """JWT의 해시 알고리즘 타입을 변경하면 올바르게 설정되는지 검증한다."""
    jwt: JWT = JWT()
    assert jwt.hash_type == HMACType.HS256
    jwt.set_hash_type(HMACType.HS512)

    assert jwt.hash_type == HMACType.HS512


def test_jwt_set_hash_type_signed() -> None:
    """서명된 JWT의 해시 알고리즘 타입을 변경하면 올바르게 설정되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.sign(Key(size=32))
    assert jwt.hash_type == HMACType.HS256
    jwt.set_hash_type(HMACType.HS512)

    assert jwt.hash_type == HMACType.HS512


def test_jwt_set_expiration() -> None:
    """JWT에 만료 시간을 설정하면 is_expired가 올바른 값을 반환하는지 검증한다."""
    jwt: JWT = JWT()
    jwt.set_expiration(timedelta(days=-1))
    assert jwt.is_expired


def test_jwt_set_expiration_signed() -> None:
    """서명된 JWT에 만료 시간을 설정하면 is_expired가 올바른 값을 반환하는지 검증한다."""
    jwt: JWT = JWT()
    jwt.sign(Key(size=32))
    jwt.set_expiration(timedelta(days=-1))
    assert jwt.is_expired


def test_jwt_set_expiration_expect_jwt_processing_error() -> None:
    """iat 필드가 없는 JWT에 만료 시간을 설정하면 JWTProcessingError가 발생하는지 검증한다."""
    jwt: JWT = JWT(
        token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.Gfx6VO9tcxwk6xqx9yYzSfebfeakZp5JYIgP_edcw_A"
    )
    with pytest.raises(
        JWTProcessingError, match="field named 'iat' does not exists in payload"
    ):
        jwt.set_expiration(timedelta(days=1))


def test_jwt_refresh() -> None:
    """JWT를 새로고침하면 만료 시간이 업데이트되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.refresh(timedelta(days=-1))
    assert jwt.is_expired


def test_jwt_refresh_signed() -> None:
    """서명된 JWT를 새로고침하면 만료 시간이 업데이트되는지 검증한다."""
    jwt: JWT = JWT()
    jwt.sign(Key(size=32))
    jwt.refresh(timedelta(days=-1))
    assert jwt.is_expired


def test_jwt_sign() -> None:
    """JWT에 서명하면 서명이 생성되고 검증에 성공하는지 검증한다."""
    jwt: JWT = JWT()
    key: Key = Key(size=32)
    jwt.sign(key)
    assert jwt.signature is not None
    assert jwt.verify(key)


def test_jwt_verify() -> None:
    """서명된 JWT를 동일한 키로 검증하면 성공하는지 확인한다."""
    jwt: JWT = JWT()
    key: Key = Key(size=32)
    jwt.sign(key)
    assert jwt.verify(key)


def test_jwt_verify_expect_fail() -> None:
    """서명된 JWT를 다른 키로 검증하면 실패하는지 확인한다."""
    jwt: JWT = JWT()
    key: Key = Key(size=32)
    jwt.sign(key)
    with pytest.raises(AssertionError):
        assert jwt.verify(Key(size=32))


def test_jwt_verify_expect_jwt_processing_error() -> None:
    """서명되지 않은 JWT를 검증하면 JWTProcessingError가 발생하는지 확인한다."""
    jwt: JWT = JWT()
    with pytest.raises(JWTProcessingError, match="signature cannot be None"):
        jwt.verify(Key(size=32))


def test_jwt_export() -> None:
    """서명된 JWT를 내보내면 빈 문자열이 아닌 토큰을 반환하는지 검증한다."""
    jwt: JWT = JWT()
    jwt.sign(Key(size=32))
    assert jwt.export() != ""


def test_jwt_export_expect_jwt_processing_error() -> None:
    """서명되지 않은 JWT를 내보내면 JWTProcessingError가 발생하는지 확인한다."""
    jwt: JWT = JWT()
    with pytest.raises(JWTProcessingError, match="Token must be signed"):
        jwt.export()
