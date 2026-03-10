from spakky.plugins.security.hash import Hash, HashType


def test_md5() -> None:
    """Hash MD5 알고리즘으로 문자열 해싱이 올바른 hex 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.MD5)
    assert result_hash.hex == "ED076287532E86365E841E92BFC50D8C"


def test_sha1() -> None:
    """Hash SHA1 알고리즘으로 문자열 해싱이 올바른 hex 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA1)
    assert result_hash.hex == "2EF7BDE608CE5404E97D5F042F95F89F1C232871"


def test_sha224() -> None:
    """Hash SHA224 알고리즘으로 문자열 해싱이 올바른 hex 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA224)
    assert result_hash.hex == "4575BB4EC129DF6380CEDDE6D71217FE0536F8FFC4E18BCA530A7A1B"


def test_sha256() -> None:
    """Hash SHA256 알고리즘으로 문자열 해싱이 올바른 hex 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA256)
    assert (
        result_hash.hex
        == "7F83B1657FF1FC53B92DC18148A1D65DFC2D4B1FA3D677284ADDD200126D9069"
    )


def test_sha256_via_file() -> None:
    """Hash SHA256으로 파일 객체 해싱이 올바른 hex 값을 반환하는지 검증."""
    with open("tests/dummy_file.txt", "rb") as file:
        result_hash: Hash = Hash(file, hash_type=HashType.SHA256)
        assert (
            result_hash.hex
            == "7F83B1657FF1FC53B92DC18148A1D65DFC2D4B1FA3D677284ADDD200126D9069"
        )


def test_sha256_b64() -> None:
    """Hash b64 속성이 올바른 Base64 인코딩 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA256)
    assert result_hash.b64 == "f4OxZX/x/FO5LcGBSKHWXfwtSx+j1ncoSt3SABJtkGk="


def test_sha256_b64_urlsafe() -> None:
    """Hash b64_urlsafe 속성이 URL-safe Base64 인코딩 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA256)
    assert result_hash.b64_urlsafe == "f4OxZX_x_FO5LcGBSKHWXfwtSx-j1ncoSt3SABJtkGk"


def test_sha256_b64_bytes() -> None:
    """Hash binary 속성이 올바른 바이트 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA256)
    assert result_hash.binary == (
        b"\x7f\x83\xb1e\x7f\xf1\xfcS\xb9-\xc1\x81H\xa1\xd6]\xfc-K\x1f\xa3\xd6w(J\xdd\xd2\x00\x12m\x90i"
    )


def test_sha384() -> None:
    """Hash SHA384 알고리즘으로 문자열 해싱이 올바른 hex 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA384)
    assert (
        result_hash.hex
        == "BFD76C0EBBD006FEE583410547C1887B0292BE76D582D96C242D2A792723E3FD6FD061F9D5CFD13B8F961358E6ADBA4A"
    )


def test_sha512() -> None:
    """Hash SHA512 알고리즘으로 문자열 해싱이 올바른 hex 값을 반환하는지 검증."""
    result_hash: Hash = Hash("Hello World!", hash_type=HashType.SHA512)
    assert (
        result_hash.hex
        == "861844D6704E8573FEC34D967E20BCFEF3D424CF48BE04E6DC08F2BD58C729743371015EAD891CC3CF1C9D34B49264B510751B1FF9E537937BC46B5D6FF4ECC8"
    )
