"""Abstract saga data model for business data.

This module provides AbstractSagaData as the base class for saga business data.
SagaData is immutable and contains only business-relevant fields.
Engine state (status, current_step, etc.) is managed by SagaResult.
"""

from dataclasses import field
from uuid import UUID, uuid4

from spakky.core.common.mutability import immutable
from spakky.domain.models.base import AbstractDomainModel


@immutable
class AbstractSagaData(AbstractDomainModel):
    """Base class for saga business data.

    Subclass this to define the data that flows through saga steps.
    Engine state is NOT included here — see SagaResult for that.
    """

    saga_id: UUID = field(default_factory=uuid4)
    """Unique identifier for this saga instance."""
