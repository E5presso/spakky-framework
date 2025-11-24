"""Annotation for lazy Pod initialization.

This module provides the @Lazy annotation to defer Pod initialization until first use.
"""

from dataclasses import dataclass

from spakky.core.annotation import ClassAnnotation


@dataclass
class Lazy(ClassAnnotation):
    """Mark a Pod for lazy initialization.

    Pods marked with @Lazy are not instantiated during application startup
    but only when first requested from the container.

    Warning:
        When using @Lazy with singleton-scoped Pods in multi-threaded environments,
        the first concurrent access may result in multiple instantiations. To ensure
        thread-safety for lazy singletons, consider using a factory pattern or
        initializing the Pod during application startup by removing @Lazy.

    Example:
        >>> @Lazy()
        >>> @Pod()
        >>> class ExpensiveService:
        >>>     def __init__(self):
        >>>         # Heavy initialization deferred until first use
        >>>         pass
    """

    ...
