from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyOutboxError(AbstractSpakkyFrameworkError, ABC): ...
