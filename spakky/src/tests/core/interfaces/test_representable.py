from spakky.core.interfaces.representable import IRepresentable


def test_representable_protocol() -> None:
    """Test that IRepresentable protocol exists and can be implemented"""

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
