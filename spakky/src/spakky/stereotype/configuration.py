"""Configuration stereotype for organizing configuration Pods.

This module provides @Configuration stereotype for grouping related
configuration and factory method Pods.
"""

from dataclasses import dataclass

from spakky.pod.annotations.pod import Pod


@dataclass(eq=False)
class Configuration(Pod):
    """Stereotype for configuration classes containing factory methods.

    Classes decorated with @Configuration typically contain @Pod-annotated
    factory methods that produce other Pods.
    """

    ...
