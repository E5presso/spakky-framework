from abc import ABC

from spakky_ddd.ports.error import AbstractSpakkyInfrastructureError


class AbstractSpakkyExternalError(AbstractSpakkyInfrastructureError, ABC): ...
