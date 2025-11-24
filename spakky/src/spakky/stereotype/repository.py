"""Repository stereotype for data access layer.

This module provides @Repository stereotype for organizing classes
that handle data persistence and retrieval.
"""

from dataclasses import dataclass

from spakky.pod.annotations.pod import Pod


@dataclass(eq=False)
class Repository(Pod):
    """Stereotype for repository classes handling data access.

    Repositories provide an abstraction over data sources,
    implementing data access patterns and queries.
    """

    ...
