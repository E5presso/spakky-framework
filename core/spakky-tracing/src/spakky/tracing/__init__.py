"""Spakky Tracing package - Distributed tracing abstraction."""

from spakky.tracing.context import TraceContext
from spakky.tracing.error import (
    AbstractSpakkyTracingError,
    InvalidTraceparentError,
)
from spakky.tracing.propagator import ITracePropagator
from spakky.tracing.w3c_propagator import W3CTracePropagator

__all__ = [
    # Context
    "TraceContext",
    # Interface
    "ITracePropagator",
    # Implementation
    "W3CTracePropagator",
    # Errors
    "AbstractSpakkyTracingError",
    "InvalidTraceparentError",
]

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-tracing")
"""Plugin identifier for the Spakky Tracing package."""
