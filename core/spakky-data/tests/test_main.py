"""공통 실행 모드에 따른 Data 플러그인의 실제 Pod 등록을 검증한다."""

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    TransactionalAspect,
)
from spakky.data.config import DataConfig
from spakky.data.main import initialize
from spakky.data.persistency.aggregate_collector import AggregateCollector


@pytest.mark.parametrize(
    "value, enabled", [("false", False), ("true", True), (None, True)]
)
def test_initialize_common_mode_expect_matching_aspects(
    monkeypatch: pytest.MonkeyPatch, value: str | None, enabled: bool
) -> None:
    """동기 Aspect는 항상 등록하고 비동기 Aspect는 공통 설정에 따라서만 등록한다."""
    if value is None:
        monkeypatch.delenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", raising=False)
    else:
        monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", value)
    application = SpakkyApplication(ApplicationContext())
    initialize(application)
    assert application.container.contains(DataConfig)
    assert application.container.contains(AggregateCollector)
    assert application.container.contains(TransactionalAspect)
    assert application.container.contains(AsyncTransactionalAspect) is enabled
    assert application.container.get(DataConfig).support_async_mode is enabled
