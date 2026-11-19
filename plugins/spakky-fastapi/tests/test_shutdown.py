"""Server shutdown signal and the @sse streams it ends."""

from asyncio import (
    CancelledError,
    create_task,
    current_task,
    get_running_loop,
    new_event_loop,
    sleep,
    timeout,
)
from contextvars import ContextVar
from collections.abc import AsyncIterator, Iterator, MutableMapping
from signal import SIG_DFL, SIGINT, SIGTERM, Signals, getsignal, signal
from threading import Thread
from types import FrameType
from typing import Any

import anyio
import pytest
from anyio import to_thread
from fastapi import FastAPI
from fastapi.testclient import TestClient
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.fastapi.shutdown import (
    ServerShutdownSignal,
    ShutdownGuardOutsideTaskError,
    ShutdownSignalRelay,
)
from tests.apps.sse import StreamJournal

FIRST_EVENTS = {
    "/stream/endless": b'data: {"state": "started"}\n\n',
    "/stream/opened-endless": b'data: {"state": "started"}\n\n',
    "/stream/sync-endless": b'data: {"number": 0}\n\n',
}


def _scope(path: str) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }


async def _stream_until_shutdown(
    api: FastAPI,
    shutdown: ServerShutdownSignal,
    path: str,
) -> list[MutableMapping[str, Any]]:
    """Open a stream whose client never leaves and shut down after one event."""
    request_delivered = False
    sent: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await anyio.sleep_forever()
        return {"type": "http.disconnect"}

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            shutdown.trigger()

    with anyio.fail_after(5):
        await api(_scope(path), receive, send)
    return sent


@pytest.mark.parametrize(
    ("path", "closed_entry"),
    [
        ("/stream/endless", "endless-closed"),
        ("/stream/opened-endless", "opened-endless-closed"),
        ("/stream/sync-endless", "sync-endless-closed"),
    ],
)
async def test_sse_stream_when_server_shuts_down_expect_normal_end_and_generator_closed(
    app: SpakkyApplication,
    api: FastAPI,
    path: str,
    closed_entry: str,
) -> None:
    """서버 종료가 시작되면 끝나지 않는 stream이 정상 응답 종료로 끝나고 generator의 finally가 실행된다."""
    shutdown = app.container.get(ServerShutdownSignal)

    sent = await _stream_until_shutdown(api, shutdown, path)

    bodies = [m for m in sent if m["type"] == "http.response.body"]
    assert sent[0]["status"] == 200
    assert bodies[0]["body"] == FIRST_EVENTS[path]
    assert bodies[-1]["more_body"] is False
    assert app.container.get(type_=StreamJournal).entries == [closed_entry]


async def test_sse_stream_opened_after_shutdown_expect_empty_normal_end(
    app: SpakkyApplication,
    api: FastAPI,
) -> None:
    """종료가 이미 시작된 뒤에 열린 stream은 generator 본문을 돌리지 않고 이벤트 없이 정상 종료한다."""
    shutdown = app.container.get(ServerShutdownSignal)
    shutdown.trigger()

    sent = await _stream_until_shutdown(api, shutdown, "/stream/endless")

    bodies = [m["body"] for m in sent if m["type"] == "http.response.body"]
    assert sent[0]["status"] == 200
    assert b"".join(bodies) == b""
    assert app.container.get(type_=StreamJournal).entries == []


def test_lifespan_shutdown_expect_signal_triggered(
    app: SpakkyApplication,
    api: FastAPI,
) -> None:
    """lifespan이 끝나면 아직 열린 stream이 끝나도록 종료 신호가 켜진다."""
    shutdown = app.container.get(ServerShutdownSignal)

    with TestClient(api):
        serving = shutdown.triggered

    assert (serving, shutdown.triggered) == (False, True)


def test_lifespan_startup_after_shutdown_expect_signal_rearmed(
    app: SpakkyApplication,
    api: FastAPI,
) -> None:
    """lifespan이 다시 시작되면 지난 종료 신호를 끄고 stream을 다시 연다."""
    shutdown = app.container.get(ServerShutdownSignal)
    shutdown.trigger()

    with TestClient(api) as client:
        serving = shutdown.triggered
        response = client.get("/stream/ticks/1")

    assert serving is False
    assert response.text == 'data: {"number": 0}\n\n'


async def test_shutdown_signal_wait_when_triggered_expect_return() -> None:
    """종료 신호를 기다리던 쪽은 trigger 후에 깨어난다."""
    shutdown = ServerShutdownSignal()
    released = anyio.Event()

    async def waiter() -> None:
        await shutdown.wait()
        released.set()

    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(waiter)
            await anyio.wait_all_tasks_blocked()
            assert not released.is_set()
            shutdown.trigger()

    assert released.is_set()


async def test_shutdown_signal_triggered_twice_expect_waiter_released_once() -> None:
    """신호 handler와 lifespan 종료가 함께 trigger해도 기다리던 쪽은 한 번 깨어난다."""
    shutdown = ServerShutdownSignal()
    released: list[str] = []

    async def waiter() -> None:
        await shutdown.wait()
        released.append("released")

    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(waiter)
            await anyio.wait_all_tasks_blocked()
            shutdown.trigger()
            shutdown.trigger()

    assert released == ["released"]


async def test_shutdown_signal_triggered_from_other_thread_expect_waiter_released() -> (
    None
):
    """다른 thread에서 trigger해도 event loop에서 기다리던 쪽이 깨어난다."""
    shutdown = ServerShutdownSignal()

    async def trigger_later() -> None:
        await anyio.wait_all_tasks_blocked()
        await to_thread.run_sync(shutdown.trigger)

    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(trigger_later)
            await shutdown.wait()

    assert shutdown.triggered is True


async def test_shutdown_signal_wait_after_trigger_expect_immediate_return() -> None:
    """이미 종료가 시작되었으면 wait는 바로 돌아온다."""
    shutdown = ServerShutdownSignal()
    shutdown.trigger()

    with anyio.fail_after(1):
        await shutdown.wait()

    assert shutdown.triggered is True


async def test_shutdown_signal_reset_expect_waiting_again() -> None:
    """reset 뒤에는 다시 종료 전 상태로 돌아가 wait가 기다린다."""
    shutdown = ServerShutdownSignal()
    shutdown.trigger()
    released = anyio.Event()

    async def waiter() -> None:
        await shutdown.wait()
        released.set()

    shutdown.reset()
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(waiter)
            await anyio.wait_all_tasks_blocked()
            still_waiting = not released.is_set()
            group.cancel_scope.cancel()

    assert shutdown.triggered is False
    assert still_waiting is True


async def test_stream_until_shutdown_when_stream_fails_expect_error_propagated() -> (
    None
):
    """stream이 실패하면 그 예외가 그대로 올라오고 stream은 닫힌다."""
    shutdown = ServerShutdownSignal()
    closed: list[str] = []

    async def failing() -> AsyncIterator[int]:
        try:
            yield 1
            raise LookupError("broken stream")
        finally:
            closed.append("closed")

    received: list[int] = []
    with pytest.raises(LookupError):
        async for item in shutdown.stream_until_shutdown(failing()):
            received.append(item)

    assert (received, closed) == ([1], ["closed"])


async def test_stream_until_shutdown_when_consumer_cancelled_expect_stream_closed() -> (
    None
):
    """소비하던 쪽이 취소되면 기다리던 항목을 취소하고 stream을 닫는다."""
    shutdown = ServerShutdownSignal()
    closed: list[str] = []
    first = anyio.Event()

    async def endless() -> AsyncIterator[int]:
        try:
            yield 1
            await anyio.sleep_forever()
            yield 2
        finally:
            closed.append("closed")

    async def consume() -> None:
        async for _ in shutdown.stream_until_shutdown(endless()):
            first.set()

    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await first.wait()
            await anyio.wait_all_tasks_blocked()
            group.cancel_scope.cancel()

    assert closed == ["closed"]


async def test_stream_until_shutdown_of_plain_async_iterator_expect_items() -> None:
    """async generator가 아닌 async iterator도 끝까지 내보낸다."""
    shutdown = ServerShutdownSignal()

    class Countdown:
        remaining = 2

        def __aiter__(self) -> "Countdown":
            return self

        async def __anext__(self) -> int:
            if self.remaining == 0:
                raise StopAsyncIteration
            self.remaining -= 1
            return self.remaining

    items = [item async for item in shutdown.stream_until_shutdown(Countdown())]

    assert items == [1, 0]


def test_iterate_until_shutdown_triggered_while_waiting_expect_item_dropped() -> None:
    """sync generator가 다음 항목을 만드는 동안 종료가 시작되면 그 항목을 버리고 끝난다."""
    shutdown = ServerShutdownSignal()
    closed: list[str] = []

    def numbers() -> Iterator[int]:
        try:
            yield 1
            shutdown.trigger()
            yield 2
        finally:
            closed.append("closed")

    items = list(shutdown.iterate_until_shutdown(numbers()))

    assert (items, closed) == ([1], ["closed"])


def test_iterate_until_shutdown_of_plain_iterator_expect_items() -> None:
    """generator가 아닌 sync iterator도 끝까지 내보낸다."""
    shutdown = ServerShutdownSignal()

    items = list(shutdown.iterate_until_shutdown(iter([1, 2])))

    assert items == [1, 2]


async def test_relay_on_server_signal_expect_shutdown_then_server_handler() -> None:
    """서버가 설치한 SIGTERM handler를 잇고, 신호가 오면 종료 신호를 켠 뒤 서버 handler를 부른다."""
    shutdown = ServerShutdownSignal()
    received: list[int] = []

    def server_handler(signal_number: int, frame: FrameType | None) -> None:
        received.append(signal_number)

    original = {sig: getsignal(sig) for sig in (SIGTERM, SIGINT)}
    signal(SIGTERM, server_handler)
    signal(SIGINT, SIG_DFL)
    relay = ShutdownSignalRelay(shutdown, get_running_loop())
    try:
        relay.install()
        installed = (getsignal(SIGTERM), getsignal(SIGINT))

        relay.relay(SIGTERM, None)
        with anyio.fail_after(5):
            await shutdown.wait()

        relay.uninstall()
        restored = getsignal(SIGTERM)
    finally:
        for sig, handler in original.items():
            signal(sig, handler)

    assert installed == (relay.relay, SIG_DFL)
    assert received == [Signals.SIGTERM]
    assert restored is server_handler


async def test_relay_uninstall_after_handler_replaced_expect_replacement_kept() -> None:
    """설치 뒤 다른 handler로 바뀌었으면 uninstall은 그 handler를 건드리지 않는다."""
    shutdown = ServerShutdownSignal()

    def server_handler(signal_number: int, frame: FrameType | None) -> None:
        return None

    def replacement(signal_number: int, frame: FrameType | None) -> None:
        return None

    original = getsignal(SIGTERM)
    signal(SIGTERM, server_handler)
    relay = ShutdownSignalRelay(shutdown, get_running_loop())
    try:
        relay.install()
        signal(SIGTERM, replacement)
        relay.uninstall()
        kept = getsignal(SIGTERM)
    finally:
        signal(SIGTERM, original)

    assert kept is replacement


async def test_relay_install_outside_main_thread_expect_handlers_untouched() -> None:
    """main thread가 아니면 signal handler를 바꾸지 않는다."""
    shutdown = ServerShutdownSignal()
    relay = ShutdownSignalRelay(shutdown, get_running_loop())
    before = getsignal(SIGTERM)

    worker = Thread(target=relay.install)
    worker.start()
    worker.join()

    assert getsignal(SIGTERM) is before


_REQUEST_LABEL: ContextVar[str] = ContextVar("request_label", default="none")


async def test_stream_until_shutdown_with_cancel_scope_across_yield_expect_items() -> (
    None
):
    """stream이 yield를 감싸는 anyio cancel scope를 열어도 같은 task에서 돌아 정상으로 끝난다."""
    shutdown = ServerShutdownSignal()

    async def bounded() -> AsyncIterator[int]:
        with anyio.move_on_after(60):
            yield 1
            yield 2

    items = [item async for item in shutdown.stream_until_shutdown(bounded())]

    assert items == [1, 2]


async def test_stream_until_shutdown_with_asyncio_timeout_expect_timeout_honoured() -> (
    None
):
    """yield를 감싸는 asyncio.timeout이 만료되면 stream이 그 시점에 스스로 끝낸다."""
    shutdown = ServerShutdownSignal()

    async def limited() -> AsyncIterator[str]:
        try:
            async with timeout(0.01):
                yield "started"
                await anyio.sleep_forever()
        except TimeoutError:
            yield "timed-out"

    with anyio.fail_after(5):
        items = [item async for item in shutdown.stream_until_shutdown(limited())]

    assert items == ["started", "timed-out"]


async def test_stream_until_shutdown_expect_stream_runs_in_consuming_task() -> None:
    """stream의 모든 항목이 소비하는 task 안에서 만들어진다."""
    shutdown = ServerShutdownSignal()
    tasks: list[object] = []

    async def numbers() -> AsyncIterator[int]:
        for number in range(3):
            tasks.append(current_task())
            yield number

    items = [item async for item in shutdown.stream_until_shutdown(numbers())]

    assert items == [0, 1, 2]
    assert tasks == [current_task()] * 3


async def test_stream_until_shutdown_triggered_while_item_handled_expect_context_reset() -> (
    None
):
    """항목을 처리하는 동안 종료가 시작되면, yield에 멈춘 generator가 같은 context에서 닫혀 token을 되돌린다."""
    shutdown = ServerShutdownSignal()
    closed: list[str] = []

    async def labelled() -> AsyncIterator[str]:
        token = _REQUEST_LABEL.set("request-1")
        try:
            yield _REQUEST_LABEL.get()
            yield "never"
        finally:
            _REQUEST_LABEL.reset(token)
            closed.append(_REQUEST_LABEL.get())

    items: list[str] = []
    async for item in shutdown.stream_until_shutdown(labelled()):
        items.append(item)
        shutdown.trigger()
        # The consumer is still busy with the item (as when it sends it), so
        # the signal is delivered while no item is awaited.
        await sleep(0)
        await sleep(0)

    assert items == ["request-1"]
    assert closed == ["none"]


async def test_stream_until_shutdown_triggered_while_waiting_expect_normal_end() -> (
    None
):
    """다음 항목을 기다리는 동안 종료가 시작되면 그 대기만 취소되고, 소비하는 task는 취소된 채로 남지 않는다."""
    shutdown = ServerShutdownSignal()
    closed: list[str] = []

    async def endless() -> AsyncIterator[int]:
        try:
            yield 1
            await anyio.sleep_forever()
            yield 2
        finally:
            closed.append("closed")

    async def stop_soon() -> None:
        await anyio.wait_all_tasks_blocked()
        shutdown.trigger()

    items: list[int] = []
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(stop_soon)
            async for item in shutdown.stream_until_shutdown(endless()):
                items.append(item)
    await sleep(0)

    task = current_task()
    assert task is not None
    assert task.cancelling() == 0
    assert items == [1]
    assert closed == ["closed"]


async def test_stream_until_shutdown_when_stream_answers_cancel_expect_item_dropped() -> (
    None
):
    """취소에 항목으로 답하는 stream이면 그 항목은 버리고 정상으로 끝난다."""
    shutdown = ServerShutdownSignal()

    async def stubborn() -> AsyncIterator[str]:
        yield "first"
        try:
            await anyio.sleep_forever()
        except CancelledError:
            yield "after-cancel"

    async def stop_soon() -> None:
        await anyio.wait_all_tasks_blocked()
        shutdown.trigger()

    items: list[str] = []
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(stop_soon)
            async for item in shutdown.stream_until_shutdown(stubborn()):
                items.append(item)

    task = current_task()
    assert task is not None
    assert task.cancelling() == 0
    assert items == ["first"]


async def test_stream_until_shutdown_outside_task_expect_error() -> None:
    """asyncio task 밖에서 돌리면 종료 신호로 끊을 대상이 없으므로 오류를 낸다."""
    shutdown = ServerShutdownSignal()

    async def numbers() -> AsyncIterator[int]:
        yield 1

    guarded = shutdown.stream_until_shutdown(numbers())
    raised: list[BaseException] = []

    def step_outside_task() -> None:
        step = guarded.__anext__()
        try:
            step.send(None)
        except ShutdownGuardOutsideTaskError as error:
            raised.append(error)
        finally:
            step.close()

    get_running_loop().call_soon(step_outside_task)
    await sleep(0)

    assert len(raised) == 1


async def test_stream_until_shutdown_waiting_in_shield_expect_wait_interrupted() -> (
    None
):
    """종료 신호는 asyncio 취소이므로 stream 안의 shield된 대기도 끊고 generator를 닫는다."""
    shutdown = ServerShutdownSignal()
    closed: list[str] = []
    never_set = anyio.Event()

    async def shielded() -> AsyncIterator[str]:
        try:
            yield "first"
            with anyio.CancelScope(shield=True):
                await never_set.wait()
            yield "never"
        finally:
            closed.append("closed")

    async def stop_soon() -> None:
        await anyio.wait_all_tasks_blocked()
        shutdown.trigger()

    items: list[str] = []
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(stop_soon)
            async for item in shutdown.stream_until_shutdown(shielded()):
                items.append(item)

    assert items == ["first"]
    assert closed == ["closed"]


async def test_stream_until_shutdown_cancelled_with_interrupt_expect_cancel_kept() -> (
    None
):
    """종료 신호와 같은 순간에 들어온 다른 취소는 삼키지 않고 그대로 올린다."""
    shutdown = ServerShutdownSignal()
    first = anyio.Event()

    async def endless() -> AsyncIterator[int]:
        yield 1
        await anyio.sleep_forever()

    async def consume() -> None:
        async for _ in shutdown.stream_until_shutdown(endless()):
            first.set()

    consumer = create_task(consume())
    await first.wait()
    await anyio.wait_all_tasks_blocked()
    shutdown.trigger()
    # Let the trigger release the waiter and run the guard's interrupt.
    await sleep(0)
    await sleep(0)
    consumer.cancel()

    with pytest.raises(CancelledError):
        await consumer


def test_relay_when_loop_closed_expect_server_handler_still_called() -> None:
    """event loop가 이미 닫혀 신호를 전하지 못해도 서버의 handler는 불린다."""
    calls: list[int] = []
    loop = new_event_loop()
    loop.close()

    def server_handler(signal_number: int, frame: FrameType | None) -> None:
        calls.append(signal_number)

    previous = signal(SIGTERM, server_handler)
    try:
        relay = ShutdownSignalRelay(ServerShutdownSignal(), loop)
        relay.install()
        try:
            with pytest.raises(RuntimeError):
                relay.relay(SIGTERM, None)
        finally:
            relay.uninstall()
    finally:
        signal(SIGTERM, previous)

    assert calls == [SIGTERM]
