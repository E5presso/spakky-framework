"""Tests for cache plugin initialization."""

from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect
from spakky.cache.main import initialize
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_initialize_expect_registers_cache_aspects_only() -> None:
    """initialize()가 cache 계약 처리 aspect만 등록하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    pod_types = {pod.type_ for pod in app.container.pods.values()}
    assert CacheAspect in pod_types
    assert AsyncCacheAspect in pod_types
