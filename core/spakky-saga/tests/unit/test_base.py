"""Unit tests for AbstractSaga base class, @saga_step decorator, and _SagaStepDescriptor."""

from abc import ABC
from dataclasses import field
from uuid import UUID, uuid4

import pytest

from spakky.core.common.mutability import immutable
from spakky.saga.base import AbstractSaga, _SagaStepDescriptor, saga_step
from spakky.saga.data import AbstractSagaData
from spakky.saga.flow import Parallel, SagaFlow, SagaStep, Transaction
from spakky.saga.result import StepStatus
from spakky.saga.status import SagaStatus
from spakky.saga.strategy import Compensate, Retry, Skip


@immutable
class _OrderSagaData(AbstractSagaData):
    order_id: UUID = field(default_factory=uuid4)


class _ConcreteSaga(AbstractSaga[_OrderSagaData]):
    """테스트용 구체 사가 클래스."""

    @saga_step
    async def create_ticket(self, data: _OrderSagaData) -> _OrderSagaData:
        """티켓 발급."""
        return data

    @saga_step
    async def cancel_ticket(self, data: _OrderSagaData) -> None:
        """티켓 취소."""

    @saga_step
    async def approve_order(self, data: _OrderSagaData) -> None:
        """주문 승인."""

    def flow(self) -> SagaFlow[_OrderSagaData]:
        """Flow 정의."""
        return SagaFlow(items=(self.create_ticket >> self.cancel_ticket,))


# --- AbstractSaga 기본 검증 ---


def test_abstract_saga_is_abc_expect_true() -> None:
    """AbstractSaga가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSaga, ABC)


def test_abstract_saga_cannot_instantiate_expect_type_error() -> None:
    """AbstractSaga를 직접 인스턴스화하면 TypeError가 발생하는지 검증한다."""
    with pytest.raises(TypeError):
        AbstractSaga()  # type: ignore[abstract] - intentional for test


# --- @saga_step 데코레이터 ---


def test_saga_step_returns_descriptor_expect_descriptor_type() -> None:
    """@saga_step 적용 메서드가 클래스 속성 수준에서 _SagaStepDescriptor로 저장되는지 검증한다."""
    assert isinstance(vars(_ConcreteSaga)["create_ticket"], _SagaStepDescriptor)
    assert isinstance(vars(_ConcreteSaga)["cancel_ticket"], _SagaStepDescriptor)
    assert isinstance(vars(_ConcreteSaga)["approve_order"], _SagaStepDescriptor)


def test_undecorated_methods_remain_plain_functions_expect_not_descriptor() -> None:
    """@saga_step 미적용 메서드는 descriptor로 래핑되지 않는지 검증한다."""

    class SagaWithPlainMethod(AbstractSaga[_OrderSagaData]):
        async def plain_async(self, data: _OrderSagaData) -> None:
            """Decorator 미적용 메서드."""

        def flow(self) -> SagaFlow[_OrderSagaData]:
            """Flow 정의."""
            return SagaFlow(items=())

    assert not isinstance(
        vars(SagaWithPlainMethod).get("plain_async"), _SagaStepDescriptor
    )


# --- 디스크립터 접근 시 SagaStep 반환 ---


def test_descriptor_instance_access_expect_saga_step() -> None:
    """인스턴스에서 @saga_step 메서드 접근 시 SagaStep이 반환되는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.create_ticket
    assert isinstance(result, SagaStep)


def test_descriptor_class_access_expect_descriptor() -> None:
    """클래스에서 @saga_step 메서드 접근 시 _SagaStepDescriptor가 반환되는지 검증한다."""
    result = _ConcreteSaga.create_ticket
    assert isinstance(result, _SagaStepDescriptor)


def test_descriptor_default_on_error_expect_compensate() -> None:
    """디스크립터로 생성된 SagaStep의 기본 on_error가 Compensate인지 검증한다."""
    saga = _ConcreteSaga()
    step_obj = saga.create_ticket
    assert isinstance(step_obj.on_error, Compensate)


# --- 연산자 사용 ---


def test_rshift_operator_expect_transaction() -> None:
    """>> 연산자로 Transaction이 생성되는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.create_ticket >> saga.cancel_ticket
    assert isinstance(result, Transaction)


def test_and_operator_expect_parallel() -> None:
    """& 연산자로 Parallel이 생성되는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.create_ticket & saga.approve_order
    assert isinstance(result, Parallel)
    assert len(result.items) == 2


def test_or_operator_expect_strategy_set() -> None:
    """| 연산자로 on_error 전략이 설정되는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.create_ticket | Retry(max_attempts=3)
    assert isinstance(result, SagaStep)
    assert isinstance(result.on_error, Retry)


def test_combined_rshift_or_expect_transaction_with_strategy() -> None:
    """(step >> compensate) | strategy가 동작하는지 검증한다."""
    saga = _ConcreteSaga()
    result = (saga.create_ticket >> saga.cancel_ticket) | Skip()
    assert isinstance(result, Transaction)
    assert isinstance(result.on_error, Skip)


# --- flow() 메서드 ---


def test_flow_returns_saga_flow_expect_correct_type() -> None:
    """flow()가 SagaFlow를 반환하는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.flow()
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 1


# --- execute() 엔진 연동 ---


@pytest.mark.asyncio
async def test_execute_runs_engine_expect_completed_result() -> None:
    """execute()가 엔진을 호출하여 SagaResult를 반환하는지 검증한다."""
    saga = _ConcreteSaga()
    data = _OrderSagaData()
    result = await saga.execute(data)
    assert result.status is SagaStatus.COMPLETED
    assert len(result.history) == 1
    assert result.history[0].status is StepStatus.COMMITTED
