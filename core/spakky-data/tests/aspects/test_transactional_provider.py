"""한쪽 실행 모드의 transaction provider만 설치한 애플리케이션을 검증한다."""

from typing import override
from unittest.mock import MagicMock

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.usecase import UseCase
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.aspects.transactional import transactional
from spakky.data.main import initialize
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)


@Pod()
class InMemoryTransaction(AbstractTransaction):
    """기본 context manager가 실제로 수행한 수명 사건을 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    @override
    def initialize(self) -> None:
        self.events.append("open")

    @override
    def commit(self) -> None:
        self.events.append("commit")

    @override
    def rollback(self) -> None:
        self.events.append("rollback")

    @override
    def dispose(self) -> None:
        self.events.append("close")


@Pod()
class AsyncInMemoryTransaction(AbstractAsyncTransaction):
    """비동기 context manager의 실제 수명 사건을 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    @override
    async def initialize(self) -> None:
        self.events.append("open")

    @override
    async def commit(self) -> None:
        self.events.append("commit")

    @override
    async def rollback(self) -> None:
        self.events.append("rollback")

    @override
    async def dispose(self) -> None:
        self.events.append("close")


@UseCase()
class ProbeUseCase:
    """트랜잭션 공급자가 없을 때 본문 실행이 차단됐는지 확인한다."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @transactional
    def execute(self) -> str:
        self.calls.append("sync")
        return "saved"

    @transactional
    async def execute_async(self) -> str:
        self.calls.append("async")
        return "saved"


@pytest.mark.parametrize("provider_first", [False, True])
def test_data_plugin_sync_provider_only_expect_start_and_sync_commit(
    provider_first: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """비동기 provider가 없어도 등록 순서와 무관하게 부팅과 동기 커밋이 성공한다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", "false")
    application = SpakkyApplication(ApplicationContext())
    if provider_first:
        application.add(InMemoryTransaction)
    initialize(application)
    if not provider_first:
        application.add(InMemoryTransaction)
    application.add(ProbeUseCase).start()
    try:
        usecase = application.container.get(ProbeUseCase)
        assert usecase.execute() == "saved"
        assert usecase.calls == ["sync"]
        assert application.container.get(InMemoryTransaction).events == [
            "open",
            "commit",
            "close",
        ]
    finally:
        application.stop()


@pytest.mark.asyncio
async def test_data_plugin_async_enabled_expect_start_and_async_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """공통 비동기 지원을 켜면 양쪽 provider로 부팅하고 비동기 커밋이 성공한다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", "true")
    application = SpakkyApplication(ApplicationContext())
    initialize(application)
    application.add(InMemoryTransaction).add(AsyncInMemoryTransaction).add(
        ProbeUseCase
    ).start()
    try:
        usecase = application.container.get(ProbeUseCase)
        assert await usecase.execute_async() == "saved"
        assert usecase.calls == ["async"]
        assert application.container.get(AsyncInMemoryTransaction).events == [
            "open",
            "commit",
            "close",
        ]
    finally:
        application.stop()


def test_data_plugin_sync_collector_expect_clear_and_context_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """동기 모드에서도 aggregate 수집·정리와 다음 컨텍스트의 격리가 유지된다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", "false")
    application = SpakkyApplication(ApplicationContext())
    initialize(application)
    application.add(InMemoryTransaction).start()
    try:
        first = application.container.get(AggregateCollector)
        aggregate = MagicMock(spec=AbstractAggregateRoot)
        first.collect(aggregate)
        assert first.all() == [aggregate]
        first.clear()
        assert first.all() == []
        first.collect(aggregate)
        application.application_context.clear_context()
        second = application.container.get(AggregateCollector)
        assert second is not first
        assert second.all() == []
        assert first.all() == [aggregate]
    finally:
        application.stop()


@pytest.mark.asyncio
async def test_injected_collector_isolates_simultaneous_async_transactions() -> None:
    """같은 주입 객체를 공유해도 동시 실행의 aggregate 목록은 서로 섞이지 않는다."""
    import asyncio

    collector = AggregateCollector()
    ready = asyncio.Event()
    release = asyncio.Event()
    first = MagicMock(spec=AbstractAggregateRoot)
    second = MagicMock(spec=AbstractAggregateRoot)

    async def collect_first() -> None:
        collector.collect(first)
        ready.set()
        await release.wait()
        assert collector.all() == [first]
        collector.clear()

    async def collect_second() -> None:
        await ready.wait()
        assert collector.all() == []
        collector.collect(second)
        assert collector.all() == [second]
        collector.clear()
        release.set()

    await asyncio.gather(collect_first(), collect_second())
    assert collector.all() == []
