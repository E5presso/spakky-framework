"""DI 통합 테스트: @Saga() 클래스가 컨테이너에서 해석되어 실행되는지 검증한다."""

from uuid import uuid4

import pytest
import spakky.saga
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.saga.status import SagaStatus
from tests.integration import apps
from tests.integration.apps.order_saga import CreateOrderSaga, OrderSagaData


@pytest.fixture(name="app", scope="module")
def app_fixture() -> SpakkyApplication:
    """DI 컨테이너와 saga 플러그인을 구성한 SpakkyApplication을 제공한다."""
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky.saga.PLUGIN_NAME})
        .scan(apps)
    )
    app.start()
    return app


def test_saga_pod_resolves_from_container_expect_saga_instance(
    app: SpakkyApplication,
) -> None:
    """@Saga() 적용 클래스가 컨테이너에서 정상 해석되는지 검증한다."""
    saga = app.container.get(type_=CreateOrderSaga)
    assert isinstance(saga, CreateOrderSaga)


@pytest.mark.anyio
async def test_resolved_saga_executes_successfully_expect_completed_result(
    app: SpakkyApplication,
) -> None:
    """컨테이너에서 해석한 사가를 실행하여 SagaResult.COMPLETED가 반환되는지 검증한다."""
    saga = app.container.get(type_=CreateOrderSaga)
    data = OrderSagaData(order_id=uuid4())
    result = await saga.execute(data)
    assert result.status is SagaStatus.COMPLETED
    assert result.data.ticket_id is not None
