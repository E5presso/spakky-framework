"""Protocol for container injection.

This module defines IContainerAware for Pods that need access to the IoC container.
"""

from abc import ABC, abstractmethod

from spakky.core.pod.interfaces.aware.aware import IAware
from spakky.core.pod.interfaces.tag_registry import ITagRegistry


class ITagRegistryAware(IAware, ABC):
    """Protocol for Pods requiring tag registry injection.

    Pods implementing this protocol will have set_tag_registry() called
    during post-processing with the tag registry instance.
    """

    @abstractmethod
    def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
        """Inject tag registry.

        Args:
            tag_registry: The tag registry instance.
        """
        ...
