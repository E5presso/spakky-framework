from spakky.core.common.interfaces.representable import IRepresentable


def test_representable_protocol() -> None:
    """IRepresentable 프로토콜이 존재하고 구현 가능함을 검증한다."""

    class SampleRepresentable:
        def __init__(self, value: str) -> None:
            self.value = value

        def __str__(self) -> str:
            return f"SampleRepresentable({self.value})"

        def __repr__(self) -> str:
            return f"<SampleRepresentable: {self.value}>"

    obj = SampleRepresentable("test")
    assert isinstance(obj, IRepresentable)
    assert str(obj) == "SampleRepresentable(test)"
    assert repr(obj) == "<SampleRepresentable: test>"
