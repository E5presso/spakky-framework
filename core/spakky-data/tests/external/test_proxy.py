from spakky.data.external.proxy import (
    IAsyncGenericProxy,
    IGenericProxy,
    ProxyModel,
)


def test_proxy_model() -> None:
    """ProxyModel 생성 및 동등성 비교가 정상 동작하는지 검증한다."""

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
    """IGenericProxy 프로토콜이 필수 메서드들을 정의하고 있는지 검증한다."""
    assert hasattr(IGenericProxy, "get")
    assert hasattr(IGenericProxy, "get_or_none")
    assert hasattr(IGenericProxy, "contains")
    assert hasattr(IGenericProxy, "range")


def test_async_generic_proxy_protocol() -> None:
    """IAsyncGenericProxy 프로토콜이 필수 메서드들을 정의하고 있는지 검증한다."""
    assert hasattr(IAsyncGenericProxy, "get")
    assert hasattr(IAsyncGenericProxy, "get_or_none")
    assert hasattr(IAsyncGenericProxy, "contains")
    assert hasattr(IAsyncGenericProxy, "range")
