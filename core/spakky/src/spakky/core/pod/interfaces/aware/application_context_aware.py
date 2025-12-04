"""Protocol for application context injection.

This module defines IApplicationContextAware for Pods that need access
to the application context.
"""

from abc import ABC, abstractmethod

from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.aware import IAware


class IApplicationContextAware(IAware, ABC):
    """Protocol for Pods requiring application context injection.

    Pods implementing this protocol will have set_application_context()
    called during post-processing with the current application context.
    """

    @abstractmethod
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject application context.

        Args:
            application_context: The application context instance.
        """
        ...
