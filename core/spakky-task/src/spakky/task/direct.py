"""Direct in-process task execution support."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from inspect import iscoroutinefunction
from typing import override

from spakky.core.common.types import get_callable_methods
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.task.error import (
    TaskApplicationContextNotFoundError,
    TaskAsyncInvocationRequiredError,
    TaskNotFoundError,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DirectTaskInvocation:
    """A direct same-process task invocation request."""

    handler_type: type[object]
    """TaskHandler type that owns the method."""

    method_name: str
    """Task method name on the handler type."""

    args: tuple[object, ...] = ()
    """Positional arguments for the task method."""

    kwargs: Mapping[str, object] = field(default_factory=dict)
    """Keyword arguments for the task method."""


@Pod()
class DirectTaskExecutor(IApplicationContextAware):
    """Execute registered tasks in the current process and context scope."""

    _application_context: IApplicationContext | None

    def __init__(self) -> None:
        self._application_context = None

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject the ApplicationContext used to resolve task handlers."""
        self._application_context = application_context

    def execute(self, invocation: DirectTaskInvocation) -> object:
        """Execute a synchronous task without clearing request-scope context."""
        method = self._resolve_method(invocation)
        if iscoroutinefunction(method):
            raise TaskAsyncInvocationRequiredError()
        return method(*invocation.args, **dict(invocation.kwargs))

    async def execute_async(self, invocation: DirectTaskInvocation) -> object:
        """Execute a task in async code without clearing request-scope context."""
        method = self._resolve_method(invocation)
        result = method(*invocation.args, **dict(invocation.kwargs))
        if isinstance(result, Awaitable):
            return await result
        return result

    def _resolve_method(
        self,
        invocation: DirectTaskInvocation,
    ) -> Callable[..., object]:
        application_context = self._required_application_context()
        handler = application_context.get(invocation.handler_type)
        for name, method in get_callable_methods(handler):
            if name == invocation.method_name:
                return method
        raise TaskNotFoundError()

    def _required_application_context(self) -> IApplicationContext:
        if self._application_context is None:
            raise TaskApplicationContextNotFoundError()
        return self._application_context
