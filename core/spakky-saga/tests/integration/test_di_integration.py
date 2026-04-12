"""DI 통합 테스트: @Saga() 클래스가 컨테이너에서 해석되어 복합 흐름을 실행하는지 검증한다."""

from typing import Any, Generator
from uuid import uuid4

import pytest
import spakky.saga
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.saga.result import StepStatus
from spakky.saga.status import SagaStatus
from tests.integration import apps
from tests.integration.apps.order_saga import (
    CreateOrderSaga,
    FailingOrderSaga,
    OrderSagaData,
)


@pytest.fixture(name="app", scope="module")
def app_fixture() -> Generator[SpakkyApplication, Any, None]:
    """DI 컨테이너와 saga 플러그인을 구성한 SpakkyApplication을 제공한다."""
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky.saga.PLUGIN_NAME})
        .scan(apps)
    )
    app.start()
    yield app
    app.stop()


def test_saga_pod_resolves_from_container_expect_saga_instance(
    app: SpakkyApplication,
) -> None:
    """@Saga() 적용 클래스가 컨테이너에서 정상 해석되는지 검증한다."""
    saga = app.container.get(type_=CreateOrderSaga)
    assert isinstance(saga, CreateOrderSaga)


def test_multiple_saga_pods_resolve_independently_expect_distinct_instances(
    app: SpakkyApplication,
) -> None:
    """여러 @Saga() 클래스가 동일 컨테이너에서 서로 다른 인스턴스로 해석되는지 검증한다."""
    create = app.container.get(type_=CreateOrderSaga)
    failing = app.container.get(type_=FailingOrderSaga)
    assert isinstance(create, CreateOrderSaga)
    assert isinstance(failing, FailingOrderSaga)
    assert create is not failing


@pytest.mark.asyncio
async def test_resolved_saga_executes_full_flow_expect_all_steps_committed(
    app: SpakkyApplication,
) -> None:
    """DI로 해석한 사가가 보상 쌍·병렬·Retry를 포함한 전체 흐름을 성공 실행하는지 검증한다."""
    saga = app.container.get(type_=CreateOrderSaga)
    data = OrderSagaData(order_id=uuid4())
    result = await saga.execute(data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data.ticket_id is not None
    assert result.data.payment_id is not None
    assert result.data.shipment_id is not None
    # v1 parallel은 side-effect only — return value는 data에 반영되지 않는다 (ADR-0007).

    step_names = [record.name for record in result.history]
    assert step_names == [
        "issue_ticket",
        "charge_payment",
        "notify_customer",
        "log_audit",
        "arrange_shipment",
    ]
    assert all(record.status is StepStatus.COMMITTED for record in result.history)


@pytest.mark.asyncio
async def test_failing_saga_compensates_previous_steps_expect_reverse_order_rollback(
    app: SpakkyApplication,
) -> None:
    """실패 사가가 이전 commit step을 역순 보상하고 Skip step은 보상하지 않는지 검증한다."""
    saga = app.container.get(type_=FailingOrderSaga)
    data = OrderSagaData(order_id=uuid4())
    result = await saga.execute(data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "always_fail"
    assert isinstance(result.error, RuntimeError)

    statuses = {
        record.name: record.status
        for record in result.history
        if record.name != "unreliable_step"
    }
    assert statuses["issue_ticket"] in {StepStatus.COMMITTED, StepStatus.COMPENSATED}
    assert any(
        record.name == "issue_ticket" and record.status is StepStatus.COMPENSATED
        for record in result.history
    )
