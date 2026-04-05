"""Unit tests for AbstractSaga base class and _SagaStepDescriptor."""

from abc import ABC
from dataclasses import field
from uuid import UUID, uuid4

import pytest

from spakky.core.common.mutability import immutable
from spakky.saga.base import AbstractSaga, _SagaStepDescriptor
from spakky.saga.data import AbstractSagaData
from spakky.saga.error import SagaEngineNotConnectedError
from spakky.saga.flow import SagaFlow, SagaStep, Transaction
from spakky.saga.strategy import Compensate, Retry, Skip


@immutable
class _OrderSagaData(AbstractSagaData):
    order_id: UUID = field(default_factory=uuid4)


class _ConcreteSaga(AbstractSaga[_OrderSagaData]):
    """테스트용 구체 사가 클래스."""

    async def create_ticket(self, data: _OrderSagaData) -> _OrderSagaData:
        return data

    async def cancel_ticket(self, data: _OrderSagaData) -> None:
        return None

    async def approve_order(self, data: _OrderSagaData) -> None:
        return None

    def flow(self) -> SagaFlow[_OrderSagaData]:
        # fmt: off
        return SagaFlow(
            items=(self.create_ticket >> self.cancel_ticket,),  # pyrefly: ignore - descriptor wrapping at runtime
        )
        # fmt: on


# --- AbstractSaga 기본 검증 ---


def test_abstract_saga_is_abc_expect_true() -> None:
    """AbstractSaga가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSaga, ABC)


def test_abstract_saga_cannot_instantiate_expect_type_error() -> None:
    """AbstractSaga를 직접 인스턴스화하면 TypeError가 발생하는지 검증한다."""
    with pytest.raises(TypeError):
        AbstractSaga()  # type: ignore[abstract] - intentional for test


# --- __init_subclass__ 디스크립터 래핑 ---


def test_init_subclass_wraps_public_async_methods_expect_descriptor() -> None:
    """공개 비동기 메서드가 _SagaStepDescriptor로 래핑되는지 검증한다."""
    assert isinstance(vars(_ConcreteSaga)["create_ticket"], _SagaStepDescriptor)
    assert isinstance(vars(_ConcreteSaga)["cancel_ticket"], _SagaStepDescriptor)
    assert isinstance(vars(_ConcreteSaga)["approve_order"], _SagaStepDescriptor)


def test_init_subclass_skips_flow_method_expect_not_wrapped() -> None:
    """flow() 메서드가 래핑되지 않는지 검증한다."""
    assert not isinstance(vars(_ConcreteSaga).get("flow"), _SagaStepDescriptor)


def test_init_subclass_skips_private_methods_expect_not_wrapped() -> None:
    """private 메서드가 래핑되지 않는지 검증한다."""

    class SagaWithPrivate(AbstractSaga[_OrderSagaData]):
        async def _internal(self, data: _OrderSagaData) -> None:
            return None

        def flow(self) -> SagaFlow[_OrderSagaData]:
            return SagaFlow(items=())

    assert not isinstance(vars(SagaWithPrivate).get("_internal"), _SagaStepDescriptor)


def test_init_subclass_skips_sync_methods_expect_not_wrapped() -> None:
    """동기 메서드가 래핑되지 않는지 검증한다."""

    class SagaWithSync(AbstractSaga[_OrderSagaData]):
        def helper(self) -> str:
            return "not wrapped"

        def flow(self) -> SagaFlow[_OrderSagaData]:
            return SagaFlow(items=())

    assert not isinstance(vars(SagaWithSync).get("helper"), _SagaStepDescriptor)


# --- 디스크립터 접근 시 SagaStep 반환 ---


def test_descriptor_instance_access_expect_saga_step() -> None:
    """인스턴스에서 래핑된 메서드 접근 시 SagaStep이 반환되는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.create_ticket
    assert isinstance(result, SagaStep)


def test_descriptor_class_access_expect_descriptor() -> None:
    """클래스에서 래핑된 메서드 접근 시 _SagaStepDescriptor가 반환되는지 검증한다."""
    result = _ConcreteSaga.create_ticket  # type: ignore[attr-defined] - descriptor access
    assert isinstance(result, _SagaStepDescriptor)


def test_descriptor_default_on_error_expect_compensate() -> None:
    """디스크립터로 생성된 SagaStep의 기본 on_error가 Compensate인지 검증한다."""
    saga = _ConcreteSaga()
    # fmt: off
    step = saga.create_ticket  # pyrefly: ignore - descriptor returns SagaStep at runtime
    assert isinstance(step.on_error, Compensate)  # pyrefly: ignore - SagaStep has on_error
    # fmt: on


# --- 연산자 사용 ---


def test_rshift_operator_expect_transaction() -> None:
    """>> 연산자로 Transaction이 생성되는지 검증한다."""
    saga = _ConcreteSaga()
    # fmt: off
    result = saga.create_ticket >> saga.cancel_ticket  # pyrefly: ignore - descriptor enables >> operator
    # fmt: on
    assert isinstance(result, Transaction)


def test_and_operator_expect_parallel() -> None:
    """& 연산자로 Parallel이 생성되는지 검증한다."""
    from spakky.saga.flow import Parallel

    saga = _ConcreteSaga()
    # fmt: off
    result = saga.create_ticket & saga.approve_order  # pyrefly: ignore - descriptor enables & operator
    # fmt: on
    assert isinstance(result, Parallel)
    assert len(result.items) == 2


def test_or_operator_expect_strategy_set() -> None:
    """| 연산자로 on_error 전략이 설정되는지 검증한다."""
    saga = _ConcreteSaga()
    # fmt: off
    result = saga.create_ticket | Retry(max_attempts=3)  # pyrefly: ignore - descriptor enables | operator
    # fmt: on
    assert isinstance(result, SagaStep)
    assert isinstance(result.on_error, Retry)


def test_combined_rshift_or_expect_transaction_with_strategy() -> None:
    """(step >> compensate) | strategy가 동작하는지 검증한다."""
    saga = _ConcreteSaga()
    # fmt: off
    result = (saga.create_ticket >> saga.cancel_ticket) | Skip()  # pyrefly: ignore - descriptor enables operators
    # fmt: on
    assert isinstance(result, Transaction)
    assert isinstance(result.on_error, Skip)


# --- flow() 메서드 ---


def test_flow_returns_saga_flow_expect_correct_type() -> None:
    """flow()가 SagaFlow를 반환하는지 검증한다."""
    saga = _ConcreteSaga()
    result = saga.flow()
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 1


# --- execute() 스텁 ---


@pytest.mark.anyio
async def test_execute_stub_expect_engine_not_connected_error() -> None:
    """execute() 호출 시 SagaEngineNotConnectedError가 발생하는지 검증한다."""
    saga = _ConcreteSaga()
    data = _OrderSagaData()
    with pytest.raises(SagaEngineNotConnectedError):
        await saga.execute(data)
