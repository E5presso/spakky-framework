from spakky.core.common.interfaces.representable import IRepresentable


def test_representable_protocol() -> None:
    """IRepresentable 프로토콜이 존재하고 구현 가능함을 검증한다."""

    class TestRepresentable:
        def __init__(self, value: str) -> None:
            self.value = value

        def __str__(self) -> str:
            return f"TestRepresentable({self.value})"

        def __repr__(self) -> str:
            return f"<TestRepresentable: {self.value}>"

    obj = TestRepresentable("test")
    assert isinstance(obj, IRepresentable)
    assert str(obj) == "TestRepresentable(test)"
    assert repr(obj) == "<TestRepresentable: test>"
