"""Tests for actuator extension registry."""

from collections.abc import Mapping

from spakky.actuator.interfaces.contributor import (
    IAsyncInfoContributor,
    IInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)
from spakky.actuator.registry import ActuatorExtensionRegistry
from spakky.actuator.result import ComponentHealthResult


class _Probe(AbstractHealthProbe):
    _name: str

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


class _AsyncProbe(AbstractAsyncHealthProbe):
    _name: str

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def check_async(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


class _Contributor(IInfoContributor):
    _name: str

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def contribute_info(self) -> Mapping[str, object]:
        return {"name": self.name}


class _AsyncContributor(IAsyncInfoContributor):
    _name: str

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def contribute_info_async(self) -> Mapping[str, object]:
        return {"name": self.name}


def test_registry_returns_extensions_sorted_by_name() -> None:
    """registry가 extension들을 이름순으로 반환하는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    probe_b = _Probe("b")
    probe_a = _Probe("a")
    async_probe_b = _AsyncProbe("b")
    async_probe_a = _AsyncProbe("a")
    contributor_b = _Contributor("b")
    contributor_a = _Contributor("a")
    async_contributor_b = _AsyncContributor("b")
    async_contributor_a = _AsyncContributor("a")

    registry.register_health_probe(probe_b)
    registry.register_health_probe(probe_a)
    registry.register_async_health_probe(async_probe_b)
    registry.register_async_health_probe(async_probe_a)
    registry.register_info_contributor(contributor_b)
    registry.register_info_contributor(contributor_a)
    registry.register_async_info_contributor(async_contributor_b)
    registry.register_async_info_contributor(async_contributor_a)

    assert registry.health_probes() == (probe_a, probe_b)
    assert registry.async_health_probes() == (async_probe_a, async_probe_b)
    assert registry.info_contributors() == (contributor_a, contributor_b)
    assert registry.async_info_contributors() == (
        async_contributor_a,
        async_contributor_b,
    )
