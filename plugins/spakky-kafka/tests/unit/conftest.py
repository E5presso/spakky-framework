"""Fixtures shared by the Kafka unit tests."""

from collections.abc import Callable, Generator
from os import environ
from typing import Any

import pytest
from spakky.event.delivery import RetryPolicy

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX
from tests.unit.harness import (
    WORKER_MODULE,
    AbstractWorkerHarness,
    AsyncWorkerHarness,
    Clock,
    SyncWorkerHarness,
)

type HarnessFactory = Callable[..., AbstractWorkerHarness]
"""Builds a worker harness: `(retry=RetryPolicy(), subscriber=None)`."""


@pytest.fixture(name="config")
def config_fixture() -> Generator[KafkaConnectionConfig, Any, None]:
    """Create a test Kafka configuration."""
    env_vars = {
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID": "test-group",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID": "test-client",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS": "localhost:9092",
    }
    original = {k: environ.get(k) for k in env_vars}
    for key, value in env_vars.items():
        environ[key] = value
    try:
        yield KafkaConnectionConfig()
    finally:
        for key, value in original.items():
            if value is None:
                environ.pop(key, None)
            else:
                environ[key] = value


@pytest.fixture(name="clock")
def clock_fixture(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """Replace the worker's clocks so waits are decided by the test."""
    clock = Clock()
    monkeypatch.setattr(f"{WORKER_MODULE}.monotonic", clock.monotonic)
    monkeypatch.setattr(f"{WORKER_MODULE}.time", clock.time)
    return clock


@pytest.fixture(name="make_harness", params=["sync", "async"])
def make_harness_fixture(
    request: pytest.FixtureRequest, config: KafkaConnectionConfig, clock: Clock
) -> HarnessFactory:
    """Build a harness of the sync or the async worker for the same scenario."""
    del clock

    def factory(
        retry: RetryPolicy | None = None, subscriber: str | None = None
    ) -> AbstractWorkerHarness:
        if retry is not None:
            config.retry = retry
        if request.param == "sync":
            return SyncWorkerHarness(config, subscriber)
        return AsyncWorkerHarness(config, subscriber)

    return factory
