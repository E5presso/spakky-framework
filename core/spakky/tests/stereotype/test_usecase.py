from spakky.core.stereotype.usecase import UseCase


def test_usecase() -> None:
    """@UseCase 데코레이터가 클래스에 올바르게 적용되고 조회되는지 검증한다."""

    @UseCase()
    class SampleService: ...

    class NonAnnotated: ...

    assert UseCase.get_or_none(SampleService) is not None
    assert UseCase.get_or_none(NonAnnotated) is None
