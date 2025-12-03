"""UseCase stereotype for encapsulating business logic.

This module provides @UseCase stereotype for organizing classes
that implement application-specific business rules.
"""

from dataclasses import dataclass

from spakky.pod.annotations.pod import Pod


@dataclass(eq=False)
class UseCase(Pod):
    """Stereotype for use case classes encapsulating business logic.

    UseCases represent application-specific business operations,
    orchestrating domain entities and services to fulfill requirements.
    """

    ...
