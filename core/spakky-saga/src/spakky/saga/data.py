"""Saga business data model."""

from abc import ABC
from dataclasses import field
from uuid import UUID, uuid4

from spakky.core.common.mutability import immutable
from spakky.domain.models.base import AbstractDomainModel


@immutable
class AbstractSagaData(AbstractDomainModel, ABC):
    """사가의 비즈니스 데이터. 엔진 상태를 포함하지 않는다."""

    saga_id: UUID = field(default_factory=uuid4)
