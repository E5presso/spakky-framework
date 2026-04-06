"""Unit tests for @Saga() stereotype."""

from spakky.core.pod.annotations.pod import Pod
from spakky.saga.stereotype import Saga


def test_saga_inherits_pod_expect_true() -> None:
    """Saga가 Pod의 서브클래스인지 검증한다."""
    assert issubclass(Saga, Pod)


def test_saga_decorator_applied_expect_annotation_present() -> None:
    """@Saga() 데코레이터가 클래스에 올바르게 적용되고 조회되는지 검증한다."""

    @Saga()
    class SampleSaga: ...

    assert Saga.get_or_none(SampleSaga) is not None


def test_saga_decorator_not_applied_expect_annotation_absent() -> None:
    """@Saga() 비적용 클래스에서 None이 반환되는지 검증한다."""

    class NonAnnotated: ...

    assert Saga.get_or_none(NonAnnotated) is None


def test_saga_decorator_inherits_pod_annotation_expect_pod_present() -> None:
    """@Saga() 적용 클래스가 Pod 어노테이션으로도 조회 가능한지 검증한다."""

    @Saga()
    class SampleSaga: ...

    assert Pod.get_or_none(SampleSaga) is not None
