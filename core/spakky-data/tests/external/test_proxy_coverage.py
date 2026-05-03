"""Test domain ports proxy for complete coverage."""

from typing_extensions import override

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.data.external.proxy import ProxyModel


def test_proxy_model_not_equal_different_type() -> None:
    """ProxyModel이 다른 타입과 비교 시 동등하지 않음을 검증한다."""

    class SampleId(IEquatable):
        def __init__(self, value: int) -> None:
            self.value = value

        @override
        def __eq__(self, other: object) -> bool:
            if not isinstance(other, SampleId):
                return False
            return self.value == other.value

        @override
        def __hash__(self) -> int:
            return hash(self.value)

    proxy1 = ProxyModel(id=SampleId(1))

    # Test with different type (not a ProxyModel)
    assert proxy1 != "not a proxy"
    assert proxy1 != 123
    assert proxy1 != SampleId(1)
