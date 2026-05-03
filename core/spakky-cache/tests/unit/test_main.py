"""Tests for cache plugin initialization."""

from spakky.cache.backends.memory import InMemoryCache
from spakky.cache.main import initialize
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_initialize_expect_registers_cache_backend() -> None:
    """initialize()가 cache core backend를 등록하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    pod_types = {pod.type_ for pod in app.container.pods.values()}
    assert InMemoryCache in pod_types
