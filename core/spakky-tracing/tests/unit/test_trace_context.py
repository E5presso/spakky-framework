"""Unit tests for TraceContext."""

import asyncio
import re

import pytest
from spakky.tracing.context import TraceContext
from spakky.tracing.error import InvalidTraceparentError


def test_new_root_trace_id_is_32_hex_expect_valid_format() -> None:
    """new_root()로 생성된 trace_id가 32자리 hex 문자열인지 검증한다."""
    ctx = TraceContext.new_root()
    assert re.fullmatch(r"[0-9a-f]{32}", ctx.trace_id)


def test_new_root_span_id_is_16_hex_expect_valid_format() -> None:
    """new_root()로 생성된 span_id가 16자리 hex 문자열인지 검증한다."""
    ctx = TraceContext.new_root()
    assert re.fullmatch(r"[0-9a-f]{16}", ctx.span_id)


def test_new_root_expect_no_parent_and_sampled() -> None:
    """new_root()로 생성된 컨텍스트가 parent_span_id=None, trace_flags=1인지 검증한다."""
    ctx = TraceContext.new_root()
    assert ctx.parent_span_id is None
    assert ctx.trace_flags == 1


def test_child_expect_same_trace_id_new_span_id() -> None:
    """child()가 동일한 trace_id, 새 span_id, parent_span_id 설정을 검증한다."""
    parent = TraceContext.new_root()
    child = parent.child()

    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id
    assert child.parent_span_id == parent.span_id
    assert child.trace_flags == parent.trace_flags


def test_to_traceparent_expect_w3c_format() -> None:
    """to_traceparent()가 W3C 형식 문자열을 생성하는지 검증한다."""
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        trace_flags=1,
    )
    assert (
        ctx.to_traceparent()
        == "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    )


def test_from_traceparent_expect_parsed_context() -> None:
    """from_traceparent()가 유효한 헤더를 올바르게 파싱하는지 검증한다."""
    header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    ctx = TraceContext.from_traceparent(header)

    assert ctx.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert ctx.span_id == "b7ad6b7169203331"
    assert ctx.trace_flags == 1


def test_from_traceparent_unsampled_expect_flags_zero() -> None:
    """from_traceparent()가 샘플링 안 된 플래그(00)를 올바르게 파싱하는지 검증한다."""
    header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-00"
    ctx = TraceContext.from_traceparent(header)
    assert ctx.trace_flags == 0


def test_from_traceparent_invalid_format_expect_error() -> None:
    """from_traceparent()가 잘못된 형식에서 InvalidTraceparentError를 발생시키는지 검증한다."""
    with pytest.raises(InvalidTraceparentError):
        TraceContext.from_traceparent("invalid-header")


def test_from_traceparent_too_few_parts_expect_error() -> None:
    """from_traceparent()가 파트 수가 부족한 입력에서 에러를 발생시키는지 검증한다."""
    with pytest.raises(InvalidTraceparentError):
        TraceContext.from_traceparent("00-abc-def")


def test_from_traceparent_wrong_length_trace_id_expect_error() -> None:
    """from_traceparent()가 길이가 맞지 않는 trace_id에서 에러를 발생시키는지 검증한다."""
    with pytest.raises(InvalidTraceparentError):
        TraceContext.from_traceparent("00-short-b7ad6b7169203331-01")


def test_roundtrip_traceparent_expect_identity() -> None:
    """to_traceparent() → from_traceparent() 왕복 변환이 동일성을 유지하는지 검증한다."""
    original = TraceContext.new_root()
    header = original.to_traceparent()
    restored = TraceContext.from_traceparent(header)

    assert restored.trace_id == original.trace_id
    assert restored.span_id == original.span_id
    assert restored.trace_flags == original.trace_flags


def test_get_set_clear_expect_contextvar_lifecycle() -> None:
    """get()/set()/clear()가 contextvars 기반 생명주기를 올바르게 관리하는지 검증한다."""
    assert TraceContext.get() is None

    ctx = TraceContext.new_root()
    TraceContext.set(ctx)
    assert TraceContext.get() is ctx

    TraceContext.clear()
    assert TraceContext.get() is None


async def test_contextvar_isolation_across_tasks_expect_independent() -> None:
    """asyncio task 간 contextvars 격리가 올바르게 동작하는지 검증한다."""
    TraceContext.clear()
    results: dict[str, str | None] = {}

    async def task_a() -> None:
        ctx_a = TraceContext.new_root()
        TraceContext.set(ctx_a)
        await asyncio.sleep(0)
        current = TraceContext.get()
        results["a"] = current.trace_id if current else None

    async def task_b() -> None:
        await asyncio.sleep(0)
        current = TraceContext.get()
        results["b"] = current.trace_id if current else None

    await asyncio.gather(task_a(), task_b())

    assert results["a"] is not None
    assert results["b"] is None
