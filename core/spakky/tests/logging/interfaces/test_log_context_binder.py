"""Tests for ILogContextBinder ABC."""

import pytest

from spakky.core.logging.interfaces.log_context_binder import ILogContextBinder


def test_log_context_binder_instantiate_expect_type_error() -> None:
    """ABC인 ILogContextBinder를 직접 인스턴스화하면 TypeError가 발생함을 검증한다."""
    with pytest.raises(TypeError):
        ILogContextBinder()  # type: ignore[abstract] # pyrefly: ignore - intentional instantiation of ABC


def test_log_context_binder_concrete_bind_expect_values_stored() -> None:
    """ILogContextBinder를 구현한 구체 클래스의 bind가 정상 동작함을 검증한다."""
    bound: dict[str, str] = {}

    class FakeBinder(ILogContextBinder):
        def bind(self, **kwargs: str) -> None:
            bound.update(kwargs)

        def unbind(self, *keys: str) -> None:
            for key in keys:
                bound.pop(key, None)

    binder = FakeBinder()
    binder.bind(trace_id="abc", span_id="def")
    assert bound == {"trace_id": "abc", "span_id": "def"}


def test_log_context_binder_concrete_unbind_expect_keys_removed() -> None:
    """ILogContextBinder를 구현한 구체 클래스의 unbind가 키를 제거함을 검증한다."""
    bound: dict[str, str] = {"a": "1", "b": "2"}

    class FakeBinder(ILogContextBinder):
        def bind(self, **kwargs: str) -> None:
            bound.update(kwargs)

        def unbind(self, *keys: str) -> None:
            for key in keys:
                bound.pop(key, None)

    binder = FakeBinder()
    binder.unbind("b")
    assert bound == {"a": "1"}
