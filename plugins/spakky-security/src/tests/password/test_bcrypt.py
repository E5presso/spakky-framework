import pytest

from spakky_security.password.bcrypt import BcryptPasswordEncoder
from spakky_security.password.interface import IPasswordEncoder


def test_bcrypt_expect_value_error() -> None:
    with pytest.raises(ValueError):
        BcryptPasswordEncoder()  # pyrefly: ignore


def test_bcrypt_not_equal() -> None:
    p1: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    assert p1 != p2


def test_bcrypt_from_hash() -> None:
    p1: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = BcryptPasswordEncoder(password_hash=p1.encode())
    assert p1 == p2


def test_bcrypt_encode() -> None:
    p1: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    assert str(p1) == p1.encode()


def test_bcrypt_repr() -> None:
    p1: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    assert repr(p1) == str(p1)


def test_bcrypt_not_equal_different_type() -> None:
    p1: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    assert p1 != "not_a_password_encoder"
    assert p1 != 123


def test_bcrypt_challenge() -> None:
    assert BcryptPasswordEncoder(password="Hello World").challenge("Hello World")


def test_bcrypt_hash() -> None:
    p1: IPasswordEncoder = BcryptPasswordEncoder(password="pa55word!!")
    p2: IPasswordEncoder = BcryptPasswordEncoder(password_hash=p1.encode())

    assert hash(p1) == hash(p2)
