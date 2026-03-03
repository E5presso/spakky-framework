from spakky.data.stereotype.repository import Repository


def test_repository() -> None:
    """@Repository 어노테이션이 클래스에 적용되고 탐지되는지 검증한다."""

    @Repository()
    class SampleRepository: ...

    class NonAnnotated: ...

    assert Repository.get_or_none(SampleRepository) is not None
    assert Repository.get_or_none(NonAnnotated) is None
