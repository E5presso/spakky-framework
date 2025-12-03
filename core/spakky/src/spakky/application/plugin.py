"""Plugin metadata representation.

This module defines the Plugin class for identifying and managing framework plugins.
"""

from spakky.core.interfaces.equatable import IEquatable
from spakky.core.mutability import immutable


@immutable
class Plugin(IEquatable):
    """Immutable plugin identifier.

    Plugins are identified by name and used to selectively load framework extensions.
    """

    name: str
    """Unique name of the plugin."""

    def __hash__(self) -> int:
        """Compute hash based on plugin name.

        Returns:
            Hash value for this plugin.
        """
        return hash(self.name)

    def __eq__(self, __value: object) -> bool:
        """Check equality based on plugin name.

        Args:
            __value: The object to compare with.

        Returns:
            True if both plugins have the same name.
        """
        if not isinstance(__value, Plugin):
            return False
        return self.name == __value.name
