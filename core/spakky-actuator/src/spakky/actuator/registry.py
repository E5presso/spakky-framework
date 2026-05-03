"""Registry for DI-managed actuator extensions."""

from spakky.core.pod.annotations.pod import Pod

from spakky.actuator.interfaces.contributor import (
    IAsyncInfoContributor,
    IInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)


@Pod()
class ActuatorExtensionRegistry:
    """In-memory registry populated from DI-managed actuator extensions."""

    _health_probes: list[AbstractHealthProbe]
    _async_health_probes: list[AbstractAsyncHealthProbe]
    _info_contributors: list[IInfoContributor]
    _async_info_contributors: list[IAsyncInfoContributor]

    def __init__(self) -> None:
        """Initialize an empty actuator extension registry."""
        self._health_probes = []
        self._async_health_probes = []
        self._info_contributors = []
        self._async_info_contributors = []

    def register_health_probe(self, probe: AbstractHealthProbe) -> None:
        """Register a synchronous health probe."""
        self._health_probes.append(probe)

    def register_async_health_probe(self, probe: AbstractAsyncHealthProbe) -> None:
        """Register an asynchronous health probe."""
        self._async_health_probes.append(probe)

    def register_info_contributor(self, contributor: IInfoContributor) -> None:
        """Register a synchronous info contributor."""
        self._info_contributors.append(contributor)

    def register_async_info_contributor(
        self, contributor: IAsyncInfoContributor
    ) -> None:
        """Register an asynchronous info contributor."""
        self._async_info_contributors.append(contributor)

    def health_probes(self) -> tuple[AbstractHealthProbe, ...]:
        """Return registered synchronous health probes sorted by name."""
        return tuple(sorted(self._health_probes, key=lambda probe: probe.name))

    def async_health_probes(self) -> tuple[AbstractAsyncHealthProbe, ...]:
        """Return registered asynchronous health probes sorted by name."""
        return tuple(sorted(self._async_health_probes, key=lambda probe: probe.name))

    def info_contributors(self) -> tuple[IInfoContributor, ...]:
        """Return registered synchronous info contributors sorted by name."""
        return tuple(
            sorted(self._info_contributors, key=lambda contributor: contributor.name)
        )

    def async_info_contributors(self) -> tuple[IAsyncInfoContributor, ...]:
        """Return registered asynchronous info contributors sorted by name."""
        return tuple(
            sorted(
                self._async_info_contributors,
                key=lambda contributor: contributor.name,
            )
        )
