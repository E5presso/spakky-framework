import random

import pytest

from spakky.plugins.security.cryptography.gcm import Gcm
from spakky.plugins.security.cryptography.interface import ICryptor
from spakky.plugins.security.error import DecryptionFailedError, KeySizeError
from spakky.plugins.security.key import Key


def test_gcm() -> None:
    """GCM 암호화기로 암호화 후 복호화하면 원본 평문이 복원되고, 위변조된 데이터는 복호화 실패하는지 검증한다."""
    cryptor: ICryptor = Gcm(key=Key(size=32))
    cipher: str = cryptor.encrypt("Hello World!")
    plain: str = cryptor.decrypt(cipher)
    assert plain == "Hello World!"
    with pytest.raises(DecryptionFailedError):
        tempered: list[str] = list(cipher)
        random.shuffle(tempered)
        tempered_cipher: str = "".join(tempered)
        plain = cryptor.decrypt(tempered_cipher)


def test_gcm_expect_key_size_error() -> None:
    """지원되지 않는 키 크기로 GCM을 생성하면 KeySizeError가 발생하는지 검증한다."""
    with pytest.raises(KeySizeError):
        Gcm(key=Key(size=64))
