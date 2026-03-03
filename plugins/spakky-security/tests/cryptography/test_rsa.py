import random

import pytest

from spakky.plugins.security.cryptography.interface import ICryptor, ISigner
from spakky.plugins.security.cryptography.rsa import AsymmetricKey, Rsa
from spakky.plugins.security.encoding import Base64Encoder
from spakky.plugins.security.error import (
    CannotImportAsymmetricKeyError,
    DecryptionFailedError,
    KeySizeError,
    PrivateKeyRequiredError,
)
from spakky.plugins.security.hash import HashType

KEY_SIZES = [1024, 2048]


@pytest.mark.parametrize("size", KEY_SIZES)
def test_rsa_encryption_with_generated_key(size: int) -> None:
    """생성된 RSA 키로 암호화 후 복호화하면 원본 평문이 복원되고, 위변조된 데이터는 실패하는지 검증한다."""
    cryptor: ICryptor = Rsa(key=AsymmetricKey(size=size))
    cipher: str = cryptor.encrypt("Hello World!")
    plain: str = cryptor.decrypt(cipher)
    assert plain == "Hello World!"
    with pytest.raises(DecryptionFailedError):
        tempered: str = "".join(random.sample(cipher, len(cipher)))
        plain = cryptor.decrypt(tempered)


@pytest.mark.parametrize("size", KEY_SIZES)
def test_rsa_decrypt_without_private_key_expect_error(size: int) -> None:
    """공개키만으로 RSA 복호화를 시도하면 PrivateKeyRequiredError가 발생하는지 검증한다."""
    cryptor: ICryptor = Rsa(
        key=AsymmetricKey(key=AsymmetricKey(size=size).public_key.binary)
    )
    cipher: str = cryptor.encrypt("Hello World!")
    with pytest.raises(PrivateKeyRequiredError):
        cryptor.decrypt(cipher)


@pytest.mark.parametrize(
    "key",
    [
        b"""-----BEGIN RSA PRIVATE KEY-----
MIICXAIBAAKBgQCIrnR6JZEw1xPkI8K1VWuJq45opto6DW5hHjDvfZ/Y+BLFO8xw
JyxjqgGZ7hVZw8gHAUpArjPzZb5ICNfSz6kAeVYMZdH0SEMr5NRFUY6m32d5MezI
DfktS3OeraalGl3ECJ+XRU1t1peSS7aleutEKl3W0SWs7TfeKnfdaVoaJQIDAQAB
AoGAXjLVhaVEdkOUquPWekDft2br48YymlXNX9N96GBM/SyjSxlWYWkuF5YAOoUy
Y8YhompKMV+d4D6bsGufyuNhVjCU7zWUc82NZ9ZtspBJaCL0T2HcWU2TbD5HTIAs
VLRCQWatqIvdiSl316VB22mO95aHY6rZbfR2Ivju6uOaxxUCQQDrgIP+mbkK3LGj
ovTJ7QaV6EdueWKswdNOotQIr81YaWisAupLj7D60t7Yx39CIhUzrMguAX92LWww
VYyHyoKTAkEAlJQCCE7DvpNAW8Qj8N3YPPT/tDp6fjEcuyf1cgLb/mzSyh1Ylu1k
lORN5b68giAyDjO3lVV416kDKKaX5XfLZwJBAJ4CiI2XDrTfBsFIYP3q7vQ9+U+C
WlaXZfPpBGMfsaOUdgqTmihArPpd6e+BSz1QKPGXCGj10FO2flSf0b56fckCQHmR
bORNRh5Nr7AmGV5AtmiR8hMOciGEn8SG2m5R5p0Tf5l+T3kWfmDROOeNnAJAw5QZ
PtICYGDc2kfNn6VS0msCQGqtovYBRrVgTtOgVD+vOyq9su6AauXpQzuGJEvfC+Mn
fMqQ9TP1ljw78GCUSiqoh+1kfCeHa7jGTOmgcy6u2dQ=
-----END RSA PRIVATE KEY-----""",
    ],
)
def test_rsa_encryption_with_existing_key(key: bytes) -> None:
    """기존 PEM 키로 RSA 암호화 후 복호화하면 원본 평문이 복원되고, 위변조된 데이터는 실패하는지 검증한다."""
    cryptor: ICryptor = Rsa(key=AsymmetricKey(key=key))
    cipher: str = cryptor.encrypt("Hello World!")
    plain: str = cryptor.decrypt(cipher)
    assert plain == "Hello World!"
    with pytest.raises(DecryptionFailedError):
        tempered: str = "".join(random.sample(cipher, len(cipher)))
        plain = cryptor.decrypt(tempered)


@pytest.mark.parametrize("size", KEY_SIZES)
def test_rsa_signing_with_generated_key(size: int) -> None:
    """생성된 RSA 키로 서명 후 검증하면 성공하고, 잘못된 공개키로는 검증 실패하는지 확인한다."""
    private_key: AsymmetricKey = AsymmetricKey(size=size)
    public_key: AsymmetricKey = AsymmetricKey(key=private_key.public_key.binary)
    wrong_public_key: AsymmetricKey = AsymmetricKey(
        key=AsymmetricKey(size=size).public_key.binary
    )
    signer: ISigner = Rsa(key=private_key)
    verifier: ISigner = Rsa(key=public_key)
    wrong_verifier: ISigner = Rsa(key=wrong_public_key)
    signature: str = signer.sign("Hello World!")
    assert verifier.verify("Hello World!", signature)
    assert wrong_verifier.verify("Hello World!", signature) is False


@pytest.mark.parametrize("size", KEY_SIZES)
def test_rsa_sign_without_private_key_expect_error(size: int) -> None:
    """공개키만으로 RSA 서명을 시도하면 PrivateKeyRequiredError가 발생하는지 검증한다."""
    signer: ISigner = Rsa(
        key=AsymmetricKey(key=AsymmetricKey(size=size).public_key.binary)
    )
    with pytest.raises(PrivateKeyRequiredError):
        signer.sign("Hello World!")


@pytest.mark.parametrize("size", KEY_SIZES)
def test_rsa_verify_forged_signature_expect_failure(size: int) -> None:
    """위조된 서명을 RSA로 검증하면 실패하는지 검증한다."""
    signer: ISigner = Rsa(key=AsymmetricKey(size=size))
    signature: str = signer.sign("Hello World!")
    assert signer.verify("Hello World!", signature) is True

    signature_bytes = list(Base64Encoder.get_bytes(signature))
    signature_bytes[-1] ^= 0xFF
    forged_siganture = Base64Encoder.from_bytes(bytes(signature_bytes))
    assert signer.verify("Hello World!", forged_siganture) is False


@pytest.mark.parametrize("size", KEY_SIZES)
def test_rsa_verify_with_wrong_hash_expect_failure(size: int) -> None:
    """잘못된 해시 알고리즘으로 RSA 서명을 검증하면 실패하는지 검증한다."""
    signer: ISigner = Rsa(key=AsymmetricKey(size=size))
    signature: str = signer.sign("Hello World!")
    assert signer.verify("Hello World!", signature) is True
    assert signer.verify("Hello World!", signature, hash_type=HashType.SHA512) is False


@pytest.mark.parametrize(
    "key",
    [
        b"""-----BEGIN RSA PRIVATE KEY-----
MIICXAIBAAKBgQCIrnR6JZEw1xPkI8K1VWuJq45opto6DW5hHjDvfZ/Y+BLFO8xw
JyxjqgGZ7hVZw8gHAUpArjPzZb5ICNfSz6kAeVYMZdH0SEMr5NRFUY6m32d5MezI
DfktS3OeraalGl3ECJ+XRU1t1peSS7aleutEKl3W0SWs7TfeKnfdaVoaJQIDAQAB
AoGAXjLVhaVEdkOUquPWekDft2br48YymlXNX9N96GBM/SyjSxlWYWkuF5YAOoUy
Y8YhompKMV+d4D6bsGufyuNhVjCU7zWUc82NZ9ZtspBJaCL0T2HcWU2TbD5HTIAs
VLRCQWatqIvdiSl316VB22mO95aHY6rZbfR2Ivju6uOaxxUCQQDrgIP+mbkK3LGj
ovTJ7QaV6EdueWKswdNOotQIr81YaWisAupLj7D60t7Yx39CIhUzrMguAX92LWww
VYyHyoKTAkEAlJQCCE7DvpNAW8Qj8N3YPPT/tDp6fjEcuyf1cgLb/mzSyh1Ylu1k
lORN5b68giAyDjO3lVV416kDKKaX5XfLZwJBAJ4CiI2XDrTfBsFIYP3q7vQ9+U+C
WlaXZfPpBGMfsaOUdgqTmihArPpd6e+BSz1QKPGXCGj10FO2flSf0b56fckCQHmR
bORNRh5Nr7AmGV5AtmiR8hMOciGEn8SG2m5R5p0Tf5l+T3kWfmDROOeNnAJAw5QZ
PtICYGDc2kfNn6VS0msCQGqtovYBRrVgTtOgVD+vOyq9su6AauXpQzuGJEvfC+Mn
fMqQ9TP1ljw78GCUSiqoh+1kfCeHa7jGTOmgcy6u2dQ=
-----END RSA PRIVATE KEY-----""",
    ],
)
def test_rsa_signing_with_existing_key(key: bytes) -> None:
    """기존 PEM 키로 RSA 서명 후 검증하면 성공하는지 확인한다."""
    private_key: AsymmetricKey = AsymmetricKey(key=key)
    public_key: AsymmetricKey = AsymmetricKey(key=private_key.public_key.binary)
    signer: ISigner = Rsa(key=private_key)
    verifier: ISigner = Rsa(key=public_key)
    signature: str = signer.sign("Hello World!")
    assert verifier.verify("Hello World!", signature)


def test_asymmetric_key_expect_key_size_error() -> None:
    """지원되지 않는 키 크기로 RSA를 생성하면 KeySizeError가 발생하는지 검증한다."""
    with pytest.raises(KeySizeError):
        Rsa(key=AsymmetricKey(size=512))
    with pytest.raises(KeySizeError):
        Rsa(
            key=AsymmetricKey(
                key=b"""-----BEGIN RSA PRIVATE KEY-----
MIIBOgIBAAJBAM/sRQOF/0MbVrq8nYdgf92X/E2JtfbyGvAky1nwexL1VuriiaE0
vopCKP1O+qiIugfl3gTbmtIle3sIqKixA9cCAwEAAQJBAMx4nFHft2yF+R+AlyXn
hzci3NJfp9umsUkR1gynilDTv5Bg+Qud2NH39PRNQmuulHQJdXCYyOMo7+Gs40FU
GjECIQD2tag7B6bIGJ1qVhE5IygexlC5DZkBQnB70XZgbI9H6QIhANfAsvqPHsPa
AhwrDj0I4wHQb83wr3VMyw1CsrP3WlW/AiBm9QyOBfVuUAdxlxV8+NUHcs/BSpFt
2yJCKfny55sr8QIgTFR+faq4xa2RZYnOBcXpGjE1/PQT/znl9JEOTCFMsl0CIDyF
JL53zbfJ0YSeewnfXuy2kBZb7nF27V/GX1FQjS7D
-----END RSA PRIVATE KEY-----"""
            )
        )


def test_asymmetric_key_expect_invalid_key_error() -> None:
    """잘못된 형식의 키로 RSA를 생성하면 CannotImportAsymmetricKeyError가 발생하는지 검증한다."""
    with pytest.raises(CannotImportAsymmetricKeyError):
        Rsa(key=AsymmetricKey(key=b"invalid key format"))


@pytest.mark.parametrize("size", KEY_SIZES)
def test_asymmetric_key_is_private_or_public(size: int) -> None:
    """AsymmetricKey의 is_private 속성이 개인키와 공개키를 올바르게 구분하는지 검증한다."""
    private_key: AsymmetricKey = AsymmetricKey(size=size)
    public_key: AsymmetricKey = AsymmetricKey(key=private_key.public_key.binary)

    assert private_key.is_private is True
    assert public_key.is_private is False
