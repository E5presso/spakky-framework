"""Post-processor for injecting framework services into aware Pods.

This module provides ApplicationContextAwareProcessor which injects
logger, container, and application context into Pods implementing aware interfaces.
"""

from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.pod.interfaces.aware.container_aware import IContainerAware
from spakky.pod.interfaces.post_processor import IPostProcessor


class ApplicationContextAwareProcessor(IPostProcessor):
    """Post-processor for injecting framework services into aware Pods.

    Checks if Pods implement aware interfaces and injects corresponding services:
    - IContainerAware: Injects IoC container
    - IApplicationContextAware: Injects application context
    - ILoggerAware: Injects logger
    """

    __application_context: IApplicationContext

    def __init__(self, application_context: IApplicationContext) -> None:
        """Initialize aware post-processor.

        Args:
            application_context: The application context to inject.
            logger: The logger to inject.
        """
        self.__application_context = application_context

    def post_process(self, pod: object) -> object:
        """Inject framework services into aware Pods.

        Args:
            pod: The Pod instance to process.

        Returns:
            The Pod instance with injected services.
        """
        if isinstance(pod, IContainerAware):
            pod.set_container(self.__application_context)
        if isinstance(pod, IApplicationContextAware):
            pod.set_application_context(self.__application_context)
        return pod
