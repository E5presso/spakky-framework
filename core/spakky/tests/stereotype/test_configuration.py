from spakky.core.stereotype.configuration import Configuration


def test_configuration() -> None:
    """@Configuration 데코레이터가 클래스에 올바르게 적용되고 조회되는지 검증한다."""

    @Configuration()
    class SampleEnvironment: ...

    class NonAnnotated: ...

    assert Configuration.get_or_none(SampleEnvironment) is not None
    assert Configuration.get_or_none(NonAnnotated) is None
