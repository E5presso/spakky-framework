"""Unit tests for saga execution structured logging."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from logging import INFO, WARNING
from uuid import UUID, uuid4

import pytest

from spakky.core.common.mutability import immutable
from spakky.saga.base import AbstractSaga
from spakky.saga.data import AbstractSagaData
from spakky.saga.engine import run_saga_flow
from spakky.saga.flow import SagaFlow, parallel, saga_flow, step
from spakky.saga.strategy import Compensate, ExponentialBackoff, Retry
from spakky.saga.stereotype import Saga


_SAGA_LOGGER = "spakky.saga.engine"


@immutable
class _OrderData(AbstractSagaData):
    order_id: UUID
    ticket_id: UUID | None = None


async def _succeed(data: _OrderData) -> None:
    """성공하는 액션."""


async def _succeed_with_data(data: _OrderData) -> _OrderData:
    """SagaData를 반환하는 액션."""
    return replace(data, ticket_id=uuid4())


async def _fail(data: _OrderData) -> None:
    """항상 실패하는 액션."""
    raise RuntimeError("step failed")


async def _compensate_noop(data: _OrderData) -> None:
    """보상 no-op."""


def _records(caplog: pytest.LogCaptureFixture) -> list[str]:
    """spakky.saga.engine 로거에서 발생한 메시지만 추출한다."""
    return [r.getMessage() for r in caplog.records if r.name == _SAGA_LOGGER]


@pytest.mark.asyncio
async def test_run_saga_flow_emits_started_and_completed_logs_expect_structured_format(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """saga 실행 시 `status=started`/`status=COMPLETED` 로그가 순서대로 출력되는지 검증한다."""
    flow: SagaFlow[_OrderData] = saga_flow(_succeed_with_data)
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    messages = _records(caplog)
    assert "[saga=OrderSaga status=started]" in messages
    assert any(
        m.startswith("[saga=OrderSaga status=COMPLETED elapsed=") for m in messages
    )


@pytest.mark.asyncio
async def test_run_saga_flow_emits_step_started_and_completed_expect_structured_format(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """각 step 시작 시 `status=started`, 성공 시 `status=completed` 로그가 출력되는지 검증한다."""
    flow: SagaFlow[_OrderData] = saga_flow(_succeed_with_data)
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    messages = _records(caplog)
    assert "[saga=OrderSaga step=_succeed_with_data status=started]" in messages
    assert any(
        m.startswith(
            "[saga=OrderSaga step=_succeed_with_data status=completed elapsed="
        )
        for m in messages
    )


@pytest.mark.asyncio
async def test_run_saga_flow_emits_failure_and_compensating_logs_expect_error_classname(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """step 실패 시 `status=failed error=<class>` + 후속 보상 로그가 출력되는지 검증한다."""
    flow: SagaFlow[_OrderData] = saga_flow(
        step(_succeed, compensate=_compensate_noop),
        _fail,
    )
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    messages = _records(caplog)
    assert "[saga=OrderSaga step=_fail status=failed error=RuntimeError]" in messages
    assert "[saga=OrderSaga step=_succeed status=compensating]" in messages
    assert any(
        m.startswith("[saga=OrderSaga step=_succeed status=compensated elapsed=")
        for m in messages
    )
    assert any(m.startswith("[saga=OrderSaga status=FAILED elapsed=") for m in messages)


@pytest.mark.asyncio
async def test_run_saga_flow_without_saga_name_expect_anonymous_placeholder(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """saga_name 생략 시 기본 익명 표기(`<anonymous>`)가 로그에 사용되는지 검증한다."""
    flow: SagaFlow[_OrderData] = saga_flow(_succeed)
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()))
    messages = _records(caplog)
    assert "[saga=<anonymous> status=started]" in messages


@pytest.mark.asyncio
async def test_run_saga_flow_parallel_group_emits_per_step_logs_expect_both_started(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """parallel 그룹의 각 step에 대해 시작/완료 로그가 개별 출력되는지 검증한다."""
    flow: SagaFlow[_OrderData] = saga_flow(parallel(_succeed, _succeed_with_data))
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    messages = _records(caplog)
    assert "[saga=OrderSaga step=_succeed status=started]" in messages
    assert "[saga=OrderSaga step=_succeed_with_data status=started]" in messages
    assert any(
        m.startswith("[saga=OrderSaga step=_succeed status=completed elapsed=")
        for m in messages
    )
    assert any(
        m.startswith(
            "[saga=OrderSaga step=_succeed_with_data status=completed elapsed="
        )
        for m in messages
    )


@pytest.mark.asyncio
async def test_run_saga_flow_retry_emits_retry_attempt_log_expect_attempt_number(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Retry 전략 적용 시 `status=retry attempt=N` 로그가 출력되는지 검증한다."""
    attempts = {"count": 0}

    async def _flaky(data: _OrderData) -> None:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient")

    retry_strategy = Retry(
        max_attempts=3,
        backoff=ExponentialBackoff(base=0.0),
        then=Compensate(),
    )
    flow: SagaFlow[_OrderData] = saga_flow(
        step(_flaky, on_error=retry_strategy),
    )
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    messages = _records(caplog)
    assert "[saga=OrderSaga step=_flaky status=retry attempt=2]" in messages


@pytest.mark.asyncio
async def test_run_saga_flow_saga_timeout_emits_timed_out_final_log_expect_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """saga 전체 타임아웃 발생 시 최종 로그가 `status=TIMED_OUT`으로 출력되는지 검증한다."""

    async def _slow(data: _OrderData) -> None:
        await asyncio.sleep(1.0)

    flow: SagaFlow[_OrderData] = saga_flow(_slow).timeout(timedelta(milliseconds=10))
    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    messages = _records(caplog)
    assert any(
        m.startswith("[saga=OrderSaga status=TIMED_OUT elapsed=") for m in messages
    )


@pytest.mark.asyncio
async def test_abstract_saga_execute_uses_class_name_as_saga_name_expect_log_tag(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`AbstractSaga.execute()`가 saga 클래스명을 로그 태그로 사용하는지 검증한다."""

    @Saga()
    class ShippingSaga(AbstractSaga[_OrderData]):
        async def ship(self, data: _OrderData) -> None:
            """Ship the order."""

        def flow(self) -> SagaFlow[_OrderData]:
            """Define saga flow."""
            return saga_flow(self.ship)

    with caplog.at_level(INFO, logger=_SAGA_LOGGER):
        await ShippingSaga().execute(_OrderData(order_id=uuid4()))
    messages = _records(caplog)
    assert "[saga=ShippingSaga status=started]" in messages


@pytest.mark.asyncio
async def test_run_saga_flow_failed_step_emits_warning_level_log_expect_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """step 실패 로그는 WARNING 레벨로 출력되는지 검증한다."""
    flow: SagaFlow[_OrderData] = saga_flow(_fail)
    with caplog.at_level(WARNING, logger=_SAGA_LOGGER):
        await run_saga_flow(flow, _OrderData(order_id=uuid4()), saga_name="OrderSaga")
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name == _SAGA_LOGGER and r.levelno == WARNING
    ]
    assert "[saga=OrderSaga step=_fail status=failed error=RuntimeError]" in warnings
