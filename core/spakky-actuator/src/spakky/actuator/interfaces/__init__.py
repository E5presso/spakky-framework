"""Actuator extension point interfaces."""

from spakky.actuator.interfaces.contributor import (
    IAsyncInfoContributor,
    IInfoContributor,
)
from spakky.actuator.interfaces.probe import (
    AbstractAsyncHealthProbe,
    AbstractHealthProbe,
)

__all__ = [
    "AbstractAsyncHealthProbe",
    "IAsyncInfoContributor",
    "AbstractHealthProbe",
    "IInfoContributor",
]
