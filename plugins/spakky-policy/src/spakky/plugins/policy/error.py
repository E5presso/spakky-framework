"""Errors raised while loading or evaluating policy documents."""


class PolicyDocumentError(Exception):
    """Base class for policy document failures."""


class PolicyDocumentLoadError(PolicyDocumentError):
    """Raised when a policy document cannot be loaded."""


class PolicyDocumentValidationError(PolicyDocumentError):
    """Raised when policy document input is not canonicalizable."""


class PolicyEvaluationError(PolicyDocumentError):
    """Raised when evaluation cannot be completed."""
