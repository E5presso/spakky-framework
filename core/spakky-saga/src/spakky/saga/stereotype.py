"""Saga stereotype for distributed transaction orchestration.

This module provides @Saga stereotype for organizing classes
that implement saga orchestration logic.
"""

from dataclasses import dataclass

from spakky.core.pod.annotations.pod import Pod


@dataclass(eq=False)
class Saga(Pod):
    """Stereotype for saga orchestration classes.

    Sagas represent distributed transaction orchestrations,
    coordinating multiple services through sequential/parallel
    steps with compensation logic.
    """

    ...
