"""Errors raised while loading or evaluating policy documents."""

from spakky.core.common.error import AbstractSpakkyFrameworkError


class PolicyDocumentError(AbstractSpakkyFrameworkError):
    """Base class for policy document failures."""

    message = "Policy document operation failed"


class PolicyDocumentLoadError(PolicyDocumentError):
    """Raised when a policy document cannot be loaded."""

    message = "Policy document could not be loaded"


class PolicyDocumentValidationError(PolicyDocumentError):
    """Raised when policy document input is not canonicalizable."""

    message = "Policy document is invalid"


class PolicyEvaluationError(PolicyDocumentError):
    """Raised when evaluation cannot be completed."""

    message = "Policy evaluation failed"
