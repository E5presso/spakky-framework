"""Post-processor for adding built-in middleware to FastAPI applications.

Automatically injects error handling and context management middleware
into FastAPI instances registered in the container.
"""

from logging import Logger

from fastapi import FastAPI
from spakky.pod.annotations.order import Order
from spakky.pod.annotations.pod import Pod
from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.pod.interfaces.post_processor import IPostProcessor

from spakky_fastapi.middlewares.error_handling import ErrorHandlingMiddleware


@Order(0)
@Pod()
class AddBuiltInMiddlewaresPostProcessor(IPostProcessor, IApplicationContextAware):
    """Post-processor that adds built-in middleware to FastAPI instances.

    Injects error handling and context management middleware into any FastAPI
    instance created as a Pod. Runs early in the post-processor chain (Order 0).
    """

    __application_context: IApplicationContext

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Set the application context for middleware injection.

        Args:
            application_context: The application context to use for middleware.
        """
        self.__application_context = application_context

    def post_process(self, pod: object) -> object:
        """Add built-in middleware to FastAPI instances.

        If the Pod is a FastAPI instance, adds error handling and context
        management middleware. Non-FastAPI Pods are returned unchanged.

        Args:
            pod: The Pod to process.

        Returns:
            The Pod, potentially with middleware added if it's a FastAPI instance.
        """
        if not isinstance(pod, FastAPI):
            return pod

        pod.add_middleware(
            ErrorHandlingMiddleware,
            logger=self.__application_context.get(Logger),
            debug=pod.debug,
        )
        return pod
