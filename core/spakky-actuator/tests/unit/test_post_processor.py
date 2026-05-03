"""Tests for actuator extension post-processor."""

from collections.abc import Mapping

from spakky.actuator.interfaces.contributor import (
    IAsyncInfoContributor,
    IInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)
from spakky.actuator.post_processor import ActuatorExtensionPostProcessor
from spakky.actuator.registry import ActuatorExtensionRegistry
from spakky.actuator.result import ComponentHealthResult


class _Probe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "probe"

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


class _Contributor(IInfoContributor):
    @property
    def name(self) -> str:
        return "contributor"

    def contribute_info(self) -> Mapping[str, object]:
        return {"name": self.name}


class _AsyncProbe(AbstractAsyncHealthProbe):
    @property
    def name(self) -> str:
        return "async-probe"

    async def check_async(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


class _AsyncContributor(_Contributor, IAsyncInfoContributor):
    async def contribute_info_async(self) -> Mapping[str, object]:
        return {"name": self.name}


def test_post_processor_registers_probe_and_contributor_expect_unmodified() -> None:
    """post_process()가 extension pod을 registry에 등록하고 원본을 반환하는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    processor = ActuatorExtensionPostProcessor(registry)
    probe = _Probe()
    contributor = _Contributor()

    probe_result = processor.post_process(probe)
    contributor_result = processor.post_process(contributor)

    assert probe_result is probe
    assert contributor_result is contributor
    assert registry.health_probes() == (probe,)
    assert registry.info_contributors() == (contributor,)


async def test_post_processor_registers_async_extensions_expect_unmodified() -> None:
    """post_process()가 async extension pod도 registry에 등록하는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    processor = ActuatorExtensionPostProcessor(registry)
    probe = _AsyncProbe()
    contributor = _AsyncContributor()

    probe_result = processor.post_process(probe)
    contributor_result = processor.post_process(contributor)

    assert probe_result is probe
    assert contributor_result is contributor
    assert registry.async_health_probes() == (probe,)
    assert registry.info_contributors() == (contributor,)
    assert registry.async_info_contributors() == (contributor,)


def test_post_processor_ignores_plain_object_expect_empty_registry() -> None:
    """post_process()가 actuator extension이 아닌 pod은 무시하는지 검증한다."""
    registry = ActuatorExtensionRegistry()
    processor = ActuatorExtensionPostProcessor(registry)
    plain = object()

    result = processor.post_process(plain)

    assert result is plain
    assert registry.health_probes() == ()
    assert registry.info_contributors() == ()
