"""ILogContextBinder — log context binding interface."""

from abc import ABC, abstractmethod


class ILogContextBinder(ABC):
    """Interface for binding contextual key-value pairs to log records.

    Implementations manage a context store (e.g., ``contextvars``) that
    structured logging filters can read from.  Plugins that need to
    enrich log records (such as ``spakky-opentelemetry``) depend on this
    interface instead of importing a concrete ``LogContext`` class
    directly, keeping plugin-to-plugin dependencies out of the graph.
    """

    @abstractmethod
    def bind(self, **kwargs: str) -> None:
        """Add key-value pairs to the current log context.

        Args:
            **kwargs: Key-value pairs to bind.
        """
        ...

    @abstractmethod
    def unbind(self, *keys: str) -> None:
        """Remove keys from the current log context.

        Args:
            *keys: Keys to remove.
        """
        ...
