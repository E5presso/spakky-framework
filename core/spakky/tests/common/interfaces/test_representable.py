from typing import override

from spakky.core.common.interfaces.representable import IRepresentable


def test_representable_interface() -> None:
    """IRepresentable 인터페이스가 명시 상속으로 구현 가능함을 검증한다."""

    class SampleRepresentable(IRepresentable):
        def __init__(self, value: str) -> None:
            self.value = value

        @override
        def __str__(self) -> str:
            return f"SampleRepresentable({self.value})"

        @override
        def __repr__(self) -> str:
            return f"<SampleRepresentable: {self.value}>"

    obj = SampleRepresentable("test")
    assert isinstance(obj, IRepresentable)
    assert str(obj) == "SampleRepresentable(test)"
    assert repr(obj) == "<SampleRepresentable: test>"
