"""Error classes for the spakky-actuator package."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyActuatorError(AbstractSpakkyFrameworkError, ABC):
    """Base class for actuator-related errors."""

    ...


class CannotEvaluateAsyncExtensionSynchronouslyError(AbstractSpakkyActuatorError):
    """Raised when a sync evaluation sees an async-only extension."""

    message = "Cannot evaluate async actuator extension synchronously"
