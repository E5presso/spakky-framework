"""Test proxy edge cases for complete coverage."""

from spakky.core.proxy import AbstractProxyHandler, ProxyFactory


def test_proxy_delete_attribute() -> None:
    """Test proxy delete attribute functionality."""

    class Target:
        def __init__(self) -> None:
            self.value = 42

    handler = AbstractProxyHandler()
    target = Target()
    proxy = ProxyFactory(target=target, handler=handler).create()

    # Verify attribute exists
    assert hasattr(proxy, "value")

    # Delete attribute through proxy
    delattr(proxy, "value")

    # Verify attribute is deleted
    assert not hasattr(proxy, "value")


def test_proxy_set_attribute() -> None:
    """Test proxy set attribute functionality."""

    class Target:
        def __init__(self) -> None:
            self.value = 42

    handler = AbstractProxyHandler()
    target = Target()
    proxy = ProxyFactory(target=target, handler=handler).create()

    # Set attribute through proxy
    proxy.new_value = 100  # pyrefly: ignore

    # Verify attribute is set on target
    assert target.new_value == 100  # pyrefly: ignore
