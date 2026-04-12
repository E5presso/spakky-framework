import pytest

from spakky.plugins.security.error import PasswordRequiredError
from spakky.plugins.security.password.bcrypt import BcryptPasswordEncoder
from spakky.plugins.security.password.interface import IPasswordEncoder

# Use low rounds for fast test execution (default is 12)
TEST_ROUNDS = 4


def test_bcrypt_expect_value_error() -> None:
    """인자 없이 BcryptPasswordEncoder를 생성하면 PasswordRequiredError가 발생하는지 검증한다."""
    with pytest.raises(PasswordRequiredError):
        BcryptPasswordEncoder()  # type: ignore[call-overload] - intentional invalid call for test


def test_bcrypt_not_equal() -> None:
    """동일한 비밀번호로 생성한 두 Bcrypt 인코더가 서로 다른지 검증한다 (무작위 솔트 사용)."""
    p1: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    p2: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    assert p1 != p2


def test_bcrypt_from_hash() -> None:
    """인코딩된 해시로부터 Bcrypt 인코더를 생성하면 원본과 동등한지 검증한다."""
    p1: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    p2: IPasswordEncoder = BcryptPasswordEncoder(password_hash=p1.encode())
    assert p1 == p2


def test_bcrypt_encode() -> None:
    """Bcrypt 인코더의 str 변환이 encode() 결과와 동일한지 검증한다."""
    p1: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    assert str(p1) == p1.encode()


def test_bcrypt_repr() -> None:
    """Bcrypt 인코더의 repr 결과가 str 결과와 동일한지 검증한다."""
    p1: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    assert repr(p1) == str(p1)


def test_bcrypt_not_equal_different_type() -> None:
    """Bcrypt 인코더를 다른 타입과 비교하면 동등하지 않음을 확인한다."""
    p1: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    assert p1 != "not_a_password_encoder"
    assert p1 != 123


def test_bcrypt_challenge() -> None:
    """Bcrypt 인코더의 challenge 메서드가 올바른 비밀번호를 검증하는지 확인한다."""
    assert BcryptPasswordEncoder(password="Hello World", rounds=TEST_ROUNDS).challenge(
        "Hello World"
    )


def test_bcrypt_hash() -> None:
    """동일한 해시로부터 생성된 두 Bcrypt 인코더의 hash 값이 동일한지 검증한다."""
    p1: IPasswordEncoder = BcryptPasswordEncoder(
        password="pa55word!!", rounds=TEST_ROUNDS
    )
    p2: IPasswordEncoder = BcryptPasswordEncoder(password_hash=p1.encode())

    assert hash(p1) == hash(p2)
