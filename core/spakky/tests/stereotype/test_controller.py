from spakky.core.stereotype.controller import Controller


def test_controller() -> None:
    """@Controller 데코레이터가 클래스에 올바르게 적용되고 조회되는지 검증한다."""

    @Controller()
    class SampleController: ...

    class NonAnnotated: ...

    assert Controller.get_or_none(SampleController) is not None
    assert Controller.get_or_none(NonAnnotated) is None
