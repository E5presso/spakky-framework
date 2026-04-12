import pytest

from spakky.plugins.security.error import PasswordRequiredError
from spakky.plugins.security.key import Key
from spakky.plugins.security.password.argon2 import Argon2PasswordEncoder
from spakky.plugins.security.password.interface import IPasswordEncoder


def test_argon2_expect_value_error() -> None:
    """인자 없이 Argon2PasswordEncoder를 생성하면 PasswordRequiredError가 발생하는지 검증한다."""
    with pytest.raises(PasswordRequiredError):
        Argon2PasswordEncoder()  # type: ignore[call-arg] - 기본값 테스트


def test_argon2_not_equal() -> None:
    """동일한 비밀번호로 생성한 두 Argon2 인코더가 서로 다른지 검증한다 (무작위 솔트 사용)."""
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    assert p1 != p2


def test_argon2_with_same_salt_equal() -> None:
    """동일한 솔트와 비밀번호로 생성한 두 Argon2 인코더가 동등한지 검증한다."""
    salt: Key = Key(size=32)
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!", salt=salt)
    p2: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!", salt=salt)
    assert p1 == p2


def test_argon2_from_hash() -> None:
    """인코딩된 해시로부터 Argon2 인코더를 생성하면 원본과 동등한지 검증한다."""
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = Argon2PasswordEncoder(password_hash=p1.encode())
    assert p1 == p2


def test_argon2_encode() -> None:
    """Argon2 인코더의 str 변환이 encode() 결과와 동일한지 검증한다."""
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    assert str(p1) == p1.encode()


def test_argon2_repr() -> None:
    """Argon2 인코더의 repr 결과가 str 결과와 동일한지 검증한다."""
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    assert repr(p1) == str(p1)


def test_argon2_not_equal_different_type() -> None:
    """Argon2 인코더를 다른 타입과 비교하면 동등하지 않음을 확인한다."""
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    assert p1 != "not_a_password_encoder"
    assert p1 != 123


def test_argon2_challenge() -> None:
    """Argon2 인코더의 challenge 메서드가 올바른 비밀번호를 검증하는지 확인한다."""
    assert Argon2PasswordEncoder(password="Hello World").challenge("Hello World")


def test_argon2_hash() -> None:
    """동일한 해시로부터 생성된 두 Argon2 인코더의 hash 값이 동일한지 검증한다."""
    p1: IPasswordEncoder = Argon2PasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = Argon2PasswordEncoder(password_hash=p1.encode())

    assert hash(p1) == hash(p2)
