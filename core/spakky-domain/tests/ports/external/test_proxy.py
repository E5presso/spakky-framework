from spakky.domain.ports.external.proxy import (
    IAsyncGenericProxy,
    IGenericProxy,
    ProxyModel,
)


def test_proxy_model() -> None:
    """Test ProxyModel creation and equality"""

    class TestId:
        def __init__(self, value: int) -> None:
            self.value = value

        def __eq__(self, other: object) -> bool:
            return isinstance(other, TestId) and self.value == other.value

        def __hash__(self) -> int:
            return hash(self.value)

    class TestProxyModel(ProxyModel[TestId]):
        pass

    model1 = TestProxyModel(id=TestId(1))
    model2 = TestProxyModel(id=TestId(1))
    model3 = TestProxyModel(id=TestId(2))

    assert model1 == model2
    assert model1 != model3
    assert hash(model1) == hash(model2)


def test_generic_proxy_protocol() -> None:
    """Test that IGenericProxy protocol exists"""
    assert hasattr(IGenericProxy, "get")
    assert hasattr(IGenericProxy, "get_or_none")
    assert hasattr(IGenericProxy, "contains")
    assert hasattr(IGenericProxy, "range")


def test_async_generic_proxy_protocol() -> None:
    """Test that IAsyncGenericProxy protocol exists"""
    assert hasattr(IAsyncGenericProxy, "get")
    assert hasattr(IAsyncGenericProxy, "get_or_none")
    assert hasattr(IAsyncGenericProxy, "contains")
    assert hasattr(IAsyncGenericProxy, "range")
