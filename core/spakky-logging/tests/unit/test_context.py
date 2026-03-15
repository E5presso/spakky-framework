"""Tests for LogContext — contextvars-based log context management."""

from spakky.logging.context import LogContext


def test_bind_and_get_expect_values_present() -> None:
    """bind()로 추가한 키-값이 get()에서 반환됨을 검증한다."""
    LogContext.clear()
    LogContext.bind(request_id="req-123", user_id="u-456")

    ctx = LogContext.get()

    assert ctx == {"request_id": "req-123", "user_id": "u-456"}
    LogContext.clear()


def test_unbind_expect_key_removed() -> None:
    """unbind()로 특정 키를 제거하면 get()에서 해당 키가 사라짐을 검증한다."""
    LogContext.clear()
    LogContext.bind(a="1", b="2", c="3")

    LogContext.unbind("b")
    ctx = LogContext.get()

    assert ctx == {"a": "1", "c": "3"}
    LogContext.clear()


def test_unbind_nonexistent_key_expect_no_error() -> None:
    """존재하지 않는 키를 unbind해도 에러가 발생하지 않음을 검증한다."""
    LogContext.clear()
    LogContext.bind(a="1")

    LogContext.unbind("nonexistent")
    ctx = LogContext.get()

    assert ctx == {"a": "1"}
    LogContext.clear()


def test_clear_expect_empty_context() -> None:
    """clear() 호출 후 컨텍스트가 비어있음을 검증한다."""
    LogContext.bind(x="1", y="2")

    LogContext.clear()
    ctx = LogContext.get()

    assert ctx == {}


def test_get_returns_copy_expect_mutation_safe() -> None:
    """get() 반환값을 변경해도 원본 컨텍스트에 영향 없음을 검증한다."""
    LogContext.clear()
    LogContext.bind(key="value")

    copy = LogContext.get()
    copy["injected"] = "hacked"

    assert LogContext.get() == {"key": "value"}
    LogContext.clear()


def test_scope_expect_temporary_binding() -> None:
    """scope() 블록 내에서만 값이 바인딩되고, 블록 종료 후 복원됨을 검증한다."""
    LogContext.clear()
    LogContext.bind(persistent="yes")

    with LogContext.scope(temp="scoped"):
        inner = LogContext.get()
        assert inner == {"persistent": "yes", "temp": "scoped"}

    outer = LogContext.get()
    assert outer == {"persistent": "yes"}
    LogContext.clear()


def test_scope_override_expect_restored_after_exit() -> None:
    """scope()로 기존 키를 덮어쓰면 블록 종료 후 원래 값으로 복원됨을 검증한다."""
    LogContext.clear()
    LogContext.bind(level="original")

    with LogContext.scope(level="overridden"):
        assert LogContext.get()["level"] == "overridden"

    assert LogContext.get()["level"] == "original"
    LogContext.clear()


def test_bind_overwrites_existing_key_expect_last_value() -> None:
    """같은 키로 bind()를 두 번 호출하면 마지막 값이 유지됨을 검증한다."""
    LogContext.clear()
    LogContext.bind(key="first")
    LogContext.bind(key="second")

    assert LogContext.get()["key"] == "second"
    LogContext.clear()
