"""Post-processor for registering services with application context.

This module provides ServicePostProcessor which automatically registers
service Pods with the application context for lifecycle management.
"""

from logging import Logger

from spakky.pod.annotations.pod import Pod
from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.post_processor import IPostProcessor
from spakky.service.interfaces.service import IAsyncService, IService


@Pod()
class ServicePostProcessor(IPostProcessor):
    """Post-processor for registering service Pods.

    Detects Pods implementing IService or IAsyncService and registers
    them with the application context for automatic lifecycle management.
    """

    __application_context: IApplicationContext
    __logger: Logger

    def __init__(
        self, application_context: IApplicationContext, logger: Logger
    ) -> None:
        """Initialize service post-processor.

        Args:
            application_context: Application context for service registration.
            logger: Logger for debugging.
        """
        super().__init__()
        self.__application_context = application_context
        self.__logger = logger

    def post_process(self, pod: object) -> object:
        """Register service Pods with application context.

        Args:
            pod: The Pod instance to process.

        Returns:
            The Pod instance unchanged.
        """
        if isinstance(pod, IService):
            pod.set_stop_event(self.__application_context.thread_stop_event)
            self.__application_context.add_service(pod)
            self.__logger.debug(
                (f"[{type(self).__name__}] {type(pod).__name__!r} added to container")
            )
        if isinstance(pod, IAsyncService):
            pod.set_stop_event(self.__application_context.task_stop_event)
            self.__application_context.add_service(pod)
            self.__logger.debug(
                (f"[{type(self).__name__}] {type(pod).__name__!r} added to container")
            )
        return pod
