"""Actuator extension registration post-processor."""

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from typing_extensions import override

from spakky.actuator.interfaces.contributor import (
    IAsyncInfoContributor,
    IInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)
from spakky.actuator.registry import ActuatorExtensionRegistry


@Pod()
class ActuatorExtensionPostProcessor(IPostProcessor):
    """Collect DI-managed actuator extension pods into the registry."""

    _registry: ActuatorExtensionRegistry

    def __init__(self, registry: ActuatorExtensionRegistry) -> None:
        """Initialize with the shared actuator extension registry."""
        self._registry = registry

    @override
    def post_process(self, pod: object) -> object:
        """Register actuator extension pods and return them unmodified."""
        if isinstance(pod, AbstractHealthProbe):
            self._registry.register_health_probe(pod)
        if isinstance(pod, AbstractAsyncHealthProbe):
            self._registry.register_async_health_probe(pod)
        if isinstance(pod, IInfoContributor):
            self._registry.register_info_contributor(pod)
        if isinstance(pod, IAsyncInfoContributor):
            self._registry.register_async_info_contributor(pod)
        return pod
