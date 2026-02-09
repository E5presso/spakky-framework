"""Tests for TableRegistrationPostProcessor."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.sqlalchemy.orm.error import InvalidTableScopeError
from spakky.plugins.sqlalchemy.orm.extractor import Extractor
from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from spakky.plugins.sqlalchemy.orm.table import Table
from spakky.plugins.sqlalchemy.orm.type_mapper import TypeMapper
from spakky.plugins.sqlalchemy.post_processors.table_registration import (
    TableRegistrationPostProcessor,
)


@dataclass
class MockPodMeta:
    """Mock pod metadata for testing."""

    target: type
    type_: type
    scope: Pod.Scope


@pytest.fixture
def model_registry() -> ModelRegistry:
    """ModelRegistry 인스턴스를 생성하는 픽스처."""
    extractor = Extractor()
    type_mapper = TypeMapper()
    return ModelRegistry(extractor, type_mapper)


def test_post_process_non_registry_expect_unchanged() -> None:
    """ModelRegistry가 아닌 pod은 변경 없이 반환되는지 검증한다."""
    processor = TableRegistrationPostProcessor()
    container = MagicMock()
    processor.set_container(container)

    pod = object()
    result = processor.post_process(pod)

    assert result is pod


def test_post_process_already_processed_expect_early_return(
    model_registry: ModelRegistry,
) -> None:
    """이미 처리된 경우 early return되는지 검증한다."""
    processor = TableRegistrationPostProcessor()
    container = MagicMock()
    container.pods = {}
    processor.set_container(container)

    # 첫 번째 처리
    processor.post_process(model_registry)

    # 두 번째 처리 - early return 검증
    result = processor.post_process(model_registry)

    assert result is model_registry


def test_post_process_invalid_scope_expect_error(
    model_registry: ModelRegistry,
) -> None:
    """DEFINITION이 아닌 scope의 @Table 클래스는 에러가 발생하는지 검증한다."""
    processor = TableRegistrationPostProcessor()

    @Table("invalid_table")
    @dataclass
    class InvalidScopeEntity:
        """Entity with invalid scope."""

        id: int

    mock_pod_meta = MockPodMeta(
        target=InvalidScopeEntity,
        type_=InvalidScopeEntity,
        scope=Pod.Scope.SINGLETON,  # DEFINITION이 아님
    )

    container = MagicMock()
    container.pods = {"invalid_scope_entity": mock_pod_meta}
    processor.set_container(container)

    with pytest.raises(InvalidTableScopeError):
        processor.post_process(model_registry)
