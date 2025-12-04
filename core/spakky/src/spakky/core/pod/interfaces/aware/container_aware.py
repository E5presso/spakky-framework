"""Protocol for container injection.

This module defines IContainerAware for Pods that need access to the IoC container.
"""

from abc import ABC, abstractmethod

from spakky.core.pod.interfaces.aware.aware import IAware
from spakky.core.pod.interfaces.container import IContainer


class IContainerAware(IAware, ABC):
    """Protocol for Pods requiring container injection.

    Pods implementing this protocol will have set_container() called
    during post-processing with the IoC container instance.
    """

    @abstractmethod
    def set_container(self, container: IContainer) -> None:
        """Inject container.

        Args:
            container: The IoC container instance.
        """
        ...
