"""LogContextBinder — Pod adapter for LogContext."""

from spakky.core.logging.interfaces.log_context_binder import ILogContextBinder
from spakky.core.pod.annotations.pod import Pod
from typing_extensions import override

from spakky.plugins.logging.context import LogContext


@Pod()
class LogContextBinder(ILogContextBinder):
    """Pod-managed adapter that delegates to LogContext classmethods.

    Registered as the ``ILogContextBinder`` implementation so that other
    plugins can depend on the core interface without importing
    ``LogContext`` directly.
    """

    @override
    def bind(self, **kwargs: str) -> None:
        """Add key-value pairs to the current log context.

        Args:
            **kwargs: Key-value pairs to bind.
        """
        LogContext.bind(**kwargs)

    @override
    def unbind(self, *keys: str) -> None:
        """Remove keys from the current log context.

        Args:
            *keys: Keys to remove.
        """
        LogContext.unbind(*keys)
