"""Test domain ports proxy for complete coverage."""

from spakky.domain.ports.external.proxy import ProxyModel


def test_proxy_model_not_equal_different_type() -> None:
    """Test ProxyModel equality with different types."""

    class TestId:
        def __init__(self, value: int) -> None:
            self.value = value

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, TestId):
                return False
            return self.value == other.value

        def __hash__(self) -> int:
            return hash(self.value)

    proxy1 = ProxyModel(id=TestId(1))

    # Test with different type (not a ProxyModel)
    assert proxy1 != "not a proxy"
    assert proxy1 != 123
    assert proxy1 != TestId(1)
