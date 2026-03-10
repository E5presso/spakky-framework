import pytest

from spakky.plugins.security.key import Key
from spakky.plugins.security.password.interface import IPasswordEncoder
from spakky.plugins.security.password.scrypt import ScryptPasswordEncoder


def test_scrypt_expect_value_error() -> None:
    """인자 없이 ScryptPasswordEncoder를 생성하면 ValueError가 발생하는지 검증한다."""
    with pytest.raises(ValueError):
        ScryptPasswordEncoder()  # type: ignore


def test_scrypt_not_equal() -> None:
    """동일한 비밀번호로 생성한 두 Scrypt 인코더가 서로 다른지 검증한다 (무작위 솔트 사용)."""
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    assert p1 != p2


def test_scrypt_with_same_salt_equal() -> None:
    """동일한 솔트와 비밀번호로 생성한 두 Scrypt 인코더가 동등한지 검증한다."""
    salt: Key = Key(size=32)
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!", salt=salt)
    p2: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!", salt=salt)
    assert p1 == p2


def test_scrypt_from_hash() -> None:
    """인코딩된 해시로부터 Scrypt 인코더를 생성하면 원본과 동등한지 검증한다."""
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = ScryptPasswordEncoder(password_hash=p1.encode())
    assert p1 == p2


def test_scrypt_encode() -> None:
    """Scrypt 인코더의 str 변환이 encode() 결과와 동일한지 검증한다."""
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    assert str(p1) == p1.encode()


def test_scrypt_repr() -> None:
    """Scrypt 인코더의 repr 결과가 str 결과와 동일한지 검증한다."""
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    assert repr(p1) == str(p1)


def test_scrypt_not_equal_different_type() -> None:
    """Scrypt 인코더를 다른 타입과 비교하면 동등하지 않음을 확인한다."""
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    assert p1 != "not_a_password_encoder"
    assert p1 != 123


def test_scrypt_challenge() -> None:
    """Scrypt 인코더의 challenge 메서드가 올바른 비밀번호를 검증하는지 확인한다."""
    assert ScryptPasswordEncoder(password="Hello World").challenge("Hello World")


def test_scrypt_hash() -> None:
    """동일한 해시로부터 생성된 두 Scrypt 인코더의 hash 값이 동일한지 검증한다."""
    p1: IPasswordEncoder = ScryptPasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = ScryptPasswordEncoder(password_hash=p1.encode())

    assert hash(p1) == hash(p2)
