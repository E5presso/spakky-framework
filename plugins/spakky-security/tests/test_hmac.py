from spakky.plugins.security.hmac_signer import HMAC, HMACType
from spakky.plugins.security.key import Key

MESSAGE: str = "Hello World! I'm Program!"


def test_hmac_hs224() -> None:
    """HMAC HS224 알고리즘으로 서명 후 검증이 성공하는지 확인."""
    key: Key = Key(size=32)
    signature: str = HMAC.sign_text(
        key=key,
        hmac_type=HMACType.HS224,
        content=MESSAGE,
    )
    assert HMAC.verify(
        key=key,
        hmac_type=HMACType.HS224,
        content=MESSAGE,
        signature=signature,
    )


def test_hmac_hs256() -> None:
    """HMAC HS256 알고리즘으로 서명 후 검증이 성공하는지 확인."""
    key: Key = Key(size=32)
    signature: str = HMAC.sign_text(
        key=key,
        hmac_type=HMACType.HS256,
        content=MESSAGE,
    )
    assert HMAC.verify(
        key=key,
        hmac_type=HMACType.HS256,
        content=MESSAGE,
        signature=signature,
    )


def test_hmac_hs384() -> None:
    """HMAC HS384 알고리즘으로 서명 후 검증이 성공하는지 확인."""
    key: Key = Key(size=32)
    signature: str = HMAC.sign_text(
        key=key,
        hmac_type=HMACType.HS384,
        content=MESSAGE,
    )
    assert HMAC.verify(
        key=key,
        hmac_type=HMACType.HS384,
        content=MESSAGE,
        signature=signature,
    )


def test_hmac_hs512() -> None:
    """HMAC HS512 알고리즘으로 서명 후 검증이 성공하는지 확인."""
    key: Key = Key(size=32)
    signature: str = HMAC.sign_text(
        key=key,
        hmac_type=HMACType.HS512,
        content=MESSAGE,
    )
    assert HMAC.verify(
        key=key,
        hmac_type=HMACType.HS512,
        content=MESSAGE,
        signature=signature,
    )
