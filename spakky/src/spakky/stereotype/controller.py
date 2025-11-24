"""Controller stereotype for grouping request handlers.

This module provides @Controller stereotype for organizing classes
that handle external requests (HTTP, CLI, etc.).
"""

from dataclasses import dataclass

from spakky.pod.annotations.pod import Pod


@dataclass(eq=False)
class Controller(Pod):
    """Stereotype for controller classes handling external requests.

    Controllers typically contain route handlers, command handlers,
    or other request processing methods.
    """

    ...
