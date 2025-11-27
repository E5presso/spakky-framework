"""Dynamic proxy implementation for intercepting object method calls and attribute access.

This module provides a proxy pattern implementation that allows intercepting and modifying
method calls and attribute access on target objects.
"""

from abc import ABC, abstractmethod
from functools import wraps
from inspect import iscoroutinefunction, ismethod
from types import new_class
from typing import Any, ClassVar, Generic, Iterable, Protocol, runtime_checkable

from spakky.core.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.types import AsyncFunc, Func, ObjectT


@runtime_checkable
class IProxyHandler(Protocol):
    """Protocol for proxy handlers that intercept object operations."""

    @abstractmethod
    def call(
        self,
        target: object,
        method: Func,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Intercept a synchronous method call.

        Args:
            target: The target object.
            method: The method being called.
            *args: Positional arguments for the method.
            **kwargs: Keyword arguments for the method.

        Returns:
            Any: The result of the method call.
        """
        ...

    @abstractmethod
    async def call_async(
        self,
        target: object,
        method: AsyncFunc,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Intercept an asynchronous method call.

        Args:
            target: The target object.
            method: The async method being called.
            *args: Positional arguments for the method.
            **kwargs: Keyword arguments for the method.

        Returns:
            Any: The result of the async method call.
        """
        ...

    @abstractmethod
    def get(self, target: object, name: str) -> Any:
        """Intercept attribute access.

        Args:
            target: The target object.
            name: The attribute name being accessed.

        Returns:
            Any: The attribute value.
        """
        ...

    @abstractmethod
    def set(self, target: object, name: str, value: Any) -> None:
        """Intercept attribute assignment.

        Args:
            target: The target object.
            name: The attribute name being set.
            value: The value being assigned.
        """
        ...

    @abstractmethod
    def delete(self, target: object, name: str) -> None:
        """Intercept attribute deletion.

        Args:
            target: The target object.
            name: The attribute name being deleted.
        """
        ...


class AbstractProxyHandler(IProxyHandler, ABC):
    """Abstract base class for proxy handlers with default pass-through implementations."""

    def call(
        self,
        target: object,
        method: Func,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Default implementation that directly calls the method.

        Args:
            target: The target object.
            method: The method being called.
            *args: Positional arguments for the method.
            **kwargs: Keyword arguments for the method.

        Returns:
            Any: The result of the method call.
        """
        return method(*args, **kwargs)

    async def call_async(
        self,
        target: object,
        method: AsyncFunc,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await method(*args, **kwargs)

    def get(self, target: object, name: str) -> Any:
        return getattr(target, name)

    def set(self, target: object, name: str, value: Any) -> None:
        return setattr(target, name, value)

    def delete(self, target: object, name: str) -> None:
        return delattr(target, name)


class ProxyFactory(Generic[ObjectT]):
    """Factory for creating dynamic proxy objects.

    Creates a proxy that intercepts method calls and attribute access on a target object,
    delegating the interception logic to a handler.
    """

    ATTRIBUTES_TO_IGNORE: ClassVar[frozenset[str]] = frozenset(
        [
            "__dict__",
            "__class__",
            "__weakref__",
            "__base__",
            "__bases__",
            "__mro__",
            "__subclasses__",
            "__name__",
            "__qualname__",
            "__module__",
            "__annotations__",
            "__doc__",
        ]
    )
    """Class-level attributes that should not be proxied."""

    _type: type[ObjectT]
    """The type of the target object."""

    _target: ObjectT
    """The target object being proxied."""

    _handler: IProxyHandler
    """The handler that implements interception logic."""

    def __init__(
        self,
        target: ObjectT,
        handler: IProxyHandler,
    ) -> None:
        """Initialize the proxy factory.

        Args:
            target: The target object to proxy.
            handler: The handler that implements interception logic.
        """
        self._type = type(target)
        self._target = target
        self._handler = handler

    def __proxy_getattribute__(self, name: str) -> Any:
        value: Any = object.__getattribute__(self._target, name)
        if ismethod(value):
            if iscoroutinefunction(value):

                @wraps(value)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await self.__proxy_call_async__(value, *args, **kwargs)

                return async_wrapper

            @wraps(value)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return self.__proxy_call__(value, *args, **kwargs)

            return wrapper
        if name in self.ATTRIBUTES_TO_IGNORE:
            return value
        return self.__proxy_getattr__(name)

    def __proxy_call__(self, method: Func, *args: Any, **kwargs: Any) -> Any:
        return self._handler.call(
            self._target,
            method,
            *args,
            **kwargs,
        )

    async def __proxy_call_async__(
        self, method: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        return await self._handler.call_async(
            self._target,
            method,
            *args,
            **kwargs,
        )

    def __proxy_getattr__(self, name: str) -> Any:
        return self._handler.get(target=self._target, name=name)

    def __proxy_setattr__(self, name: str, value: Any) -> None:
        return self._handler.set(target=self._target, name=name, value=value)

    def __proxy_delattr__(self, name: str) -> None:
        return self._handler.delete(target=self._target, name=name)

    def __proxy_dir__(self) -> Iterable[str]:
        return dir(self._target)

    def __proxy_init__(self) -> None:
        return

    def create(self) -> ObjectT:
        """Create a proxy instance for the target object.

        Returns:
            ObjectT: A proxy instance that wraps the target object.
        """
        return new_class(
            name=self._type.__name__  # pyrefly: ignore  # type: ignore
            + DYNAMIC_PROXY_CLASS_NAME_SUFFIX,
            bases=(self._type,),
            exec_body=lambda ns: ns.update(
                __getattribute__=self.__proxy_getattribute__,
                __setattr__=self.__proxy_setattr__,
                __delattr__=self.__proxy_delattr__,
                __dir__=self.__proxy_dir__,
                __init__=self.__proxy_init__,
            ),
        )()
