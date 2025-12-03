from abc import abstractmethod
from types import TracebackType
from typing import Protocol, Self, TypeVar, runtime_checkable


@runtime_checkable
class IDisposable(Protocol):
    """Interface for disposable objects."""

    @abstractmethod
    def __enter__(self) -> Self:
        """Enters the runtime context related to this object.

        Returns:
            Self: The object itself.
        """
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        """Exits the runtime context related to this object.

        Args:
            __exc_type (type[BaseException] | None): The exception type.
            __exc_value (BaseException | None): The exception value.
            __traceback (TracebackType | None): The traceback object.

        Returns:
            bool | None: True if the exception was handled, False otherwise.
        """
        raise NotImplementedError


@runtime_checkable
class IAsyncDisposable(Protocol):
    """Interface for asynchronously disposable objects."""

    @abstractmethod
    async def __aenter__(self) -> Self:
        """Asynchronously enters the runtime context related to this object.

        Returns:
            Self: The object itself.
        """
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        """Asynchronously exits the runtime context related to this object.

        Args:
            __exc_type (type[BaseException] | None): The exception type.
            __exc_value (BaseException | None): The exception value.
            __traceback (TracebackType | None): The traceback object.

        Returns:
            bool | None: True if the exception was handled, False otherwise.
        """
        raise NotImplementedError


DisposableT = TypeVar("DisposableT", bound=IDisposable)
AsyncDisposableT = TypeVar("AsyncDisposableT", bound=IAsyncDisposable)
