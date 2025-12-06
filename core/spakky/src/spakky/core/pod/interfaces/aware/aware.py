"""Base protocol for aware interfaces.

This module defines the base IAware marker protocol for dependency injection
of framework services into Pods.
"""

from abc import ABC


class IAware(ABC):
    """Marker protocol for Pods that require framework service injection.

    Implementing this protocol allows Pods to receive framework services
    like logger, container, or application context through setter injection.
    """

    ...
