"""Actuator extension point interfaces."""

from spakky.actuator.interfaces.contributor import (
    AbstractAsyncInfoContributor,
    AbstractInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)

__all__ = [
    "AbstractAsyncHealthProbe",
    "AbstractAsyncInfoContributor",
    "AbstractHealthProbe",
    "AbstractInfoContributor",
]
