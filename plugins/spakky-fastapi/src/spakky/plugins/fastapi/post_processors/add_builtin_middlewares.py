"""Post-processor for adding built-in middleware to FastAPI applications.

Automatically injects error handling and context management middleware
into FastAPI instances registered in the container.  When the tracing
plugin is loaded, tracing middleware is also added.
"""

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from fastapi import FastAPI
from spakky.plugins.fastapi.middlewares.error_handling import ErrorHandlingMiddleware
from spakky.plugins.fastapi.middlewares.tracing import TracingMiddleware
from spakky.tracing.propagator import ITracePropagator


@Order(0)
@Pod()
class AddBuiltInMiddlewaresPostProcessor(IPostProcessor, IApplicationContextAware):
    """Post-processor that adds built-in middleware to FastAPI instances.

    Injects error handling and tracing middleware into any FastAPI instance
    created as a Pod.  Tracing middleware is only added when the tracing
    plugin is loaded.  Runs early in the post-processor chain (Order 0).
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

        If the Pod is a FastAPI instance, adds error handling middleware and
        optionally tracing middleware.  Non-FastAPI Pods are returned unchanged.

        Middleware execution order (outermost first):
        1. ``TracingMiddleware`` — extract/inject W3C Trace Context
        2. ``ErrorHandlingMiddleware`` — catch exceptions → JSON responses

        ``add_middleware`` prepends, so the last added middleware executes first.

        Args:
            pod: The Pod to process.

        Returns:
            The Pod, potentially with middleware added if it's a FastAPI instance.
        """
        if not isinstance(pod, FastAPI):
            return pod

        pod.add_middleware(
            ErrorHandlingMiddleware,
            debug=pod.debug,
        )

        propagator = self.__application_context.get_or_none(ITracePropagator)
        if propagator is not None:
            pod.add_middleware(
                TracingMiddleware,
                propagator=propagator,
            )

        return pod
