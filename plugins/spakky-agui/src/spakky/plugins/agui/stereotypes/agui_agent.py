"""Backward-compatible import for the legacy @AgUiAgent marker name."""

from spakky.plugins.agui.stereotypes.agui_compatible import AGUICompatible

AgUiAgent = AGUICompatible
"""Deprecated alias for :class:`AGUICompatible`."""

__all__ = ["AgUiAgent"]
