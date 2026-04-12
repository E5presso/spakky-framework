import pytest

from spakky.plugins.security.encoding import Base64Encoder
from spakky.plugins.security.error import InvalidKeyConstructorCallError
from spakky.plugins.security.key import Key


def test_key_generate() -> None:
    """Base64 문자열로부터 Key를 생성하면 올바른 b64 값을 반환하는지 검증한다."""
    b64: str = Base64Encoder.encode(utf8="Hello World!")
    key: Key = Key(base64=b64)
    assert key.b64 == "SGVsbG8gV29ybGQh"


def test_key_from_size() -> None:
    """지정된 크기로 Key를 생성하면 해당 길이의 바이너리가 생성되는지 검증한다."""
    key: Key = Key(size=32)
    assert len(key.binary) == 32


def test_key_base64_url_safe() -> None:
    """Key의 b64와 b64_urlsafe 속성이 각각 올바른 형식을 반환하는지 검증한다."""
    b64: str = Base64Encoder.encode(utf8="My Name is Michael! Nice to meet you!")
    key: Key = Key(base64=b64)
    assert (
        key.b64 == "TXkgTmFtZSBpcyBNaWNoYWVsISBOaWNlIHRvIG1lZXQgeW91IQ=="
        and key.b64_urlsafe == "TXkgTmFtZSBpcyBNaWNoYWVsISBOaWNlIHRvIG1lZXQgeW91IQ"
    )


def test_key_from_base64() -> None:
    """표준 Base64 문자열로부터 Key를 생성하면 원본 데이터를 복원하는지 검증한다."""
    key: Key = Key(
        base64="TXkgTmFtZSBpcyBNaWNoYWVsISBOaWNlIHRvIG1lZXQgeW91IQ==",
        url_safe=False,
    )
    assert key.binary.decode("utf-8") == "My Name is Michael! Nice to meet you!"


def test_key_from_base64_url_safe() -> None:
    """URL-safe Base64 문자열로부터 Key를 생성하면 원본 데이터를 복원하는지 검증한다."""
    key: Key = Key(
        base64="TXkgTmFtZSBpcyBNaWNoYWVsISBOaWNlIHRvIG1lZXQgeW91IQ",
        url_safe=True,
    )
    assert key.binary.decode("utf-8") == "My Name is Michael! Nice to meet you!"


def test_key_expect_value_error() -> None:
    """인자 없이 Key를 생성하면 InvalidKeyConstructorCallError가 발생하는지 검증한다."""
    with pytest.raises(InvalidKeyConstructorCallError):
        Key()  # type: ignore[call-arg] - 의도적 인자 누락 테스트


def test_key_equals() -> None:
    """동일한 Base64 값으로 생성된 두 Key가 동등한지 검증한다."""
    k1: Key = Key(
        base64="TXkgTmFtZSBpcyBNaWNoYWVsISBOaWNlIHRvIG1lZXQgeW91IQ==",
        url_safe=False,
    )
    k2: Key = Key(
        base64="TXkgTmFtZSBpcyBNaWNoYWVsISBOaWNlIHRvIG1lZXQgeW91IQ==",
        url_safe=False,
    )
    assert k1 == k2


def test_key_not_equals() -> None:
    """랜덤으로 생성된 두 Key가 서로 다른지 검증한다."""
    k1: Key = Key(size=32)
    k2: Key = Key(size=32)
    assert k1 != k2


def test_key_equals_expect_type_error() -> None:
    """Key를 다른 타입과 비교하면 TypeError가 발생하는지 검증한다."""
    with pytest.raises(TypeError):
        assert Key(size=32) == 0


def test_key_length_not_equals() -> None:
    """길이가 다른 두 Key가 동등하지 않은지 검증한다."""
    k1: Key = Key(size=32)
    k2: Key = Key(size=23)
    assert k1 != k2


def test_key_hex() -> None:
    """바이너리로 생성된 Key의 hex 속성이 올바른 16진수 문자열을 반환하는지 검증한다."""
    key: Key = Key(binary=b"Hello World!")
    assert key.hex == "48656C6C6F20576F726C6421"
