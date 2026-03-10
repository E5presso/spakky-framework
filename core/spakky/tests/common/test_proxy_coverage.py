"""Test proxy edge cases for complete coverage."""

from spakky.core.common.proxy import AbstractProxyHandler, ProxyFactory


def test_proxy_delete_attribute() -> None:
    """프록시를 통한 속성 삭제 기능이 정상 동작함을 검증한다."""

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
    """프록시를 통한 속성 설정 기능이 정상 동작함을 검증한다."""

    class Target:
        def __init__(self) -> None:
            self.value = 42

    handler = AbstractProxyHandler()
    target = Target()
    proxy = ProxyFactory(target=target, handler=handler).create()

    # Set attribute through proxy
    proxy.new_value = 100  # type: ignore

    # Verify attribute is set on target
    assert target.new_value == 100  # type: ignore
