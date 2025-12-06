"""External service abstractions.

This module provides:
- Proxy pattern for external services
- External service errors
"""

from spakky.data.external.error import AbstractSpakkyExternalError
from spakky.data.external.proxy import IAsyncGenericProxy, IGenericProxy

__all__ = [
    # Proxy
    "IAsyncGenericProxy",
    "IGenericProxy",
    # Errors
    "AbstractSpakkyExternalError",
]
