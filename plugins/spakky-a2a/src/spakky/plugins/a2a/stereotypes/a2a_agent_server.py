"""Backward-compatible import for the legacy @A2AAgentServer marker name."""

from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

A2AAgentServer = A2ACompatible
"""Deprecated alias for :class:`A2ACompatible`."""

__all__ = ["A2AAgentServer"]
