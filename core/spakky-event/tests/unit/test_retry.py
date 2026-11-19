"""Field-wise overlay of retry policies declared at different layers."""

from spakky.event.retry import RetryMode, RetryPolicy


def test_retry_policy_overlay_none_expect_same_policy() -> None:
    """덮을 것이 없으면 바탕 policy를 그대로 쓴다."""
    base = RetryPolicy(max_attempts=4)
    assert base.overlay(None) is base


def test_retry_policy_overlay_expect_only_explicit_fields_replaced() -> None:
    """명시한 필드만 덮고, 기본값으로 남은 필드는 바탕 값을 지킨다."""
    base = RetryPolicy(max_attempts=5, initial_interval=1.0, mode=RetryMode.BLOCKING)

    merged = base.overlay(RetryPolicy(mode=RetryMode.DELAYED))

    assert merged == RetryPolicy(
        max_attempts=5, initial_interval=1.0, mode=RetryMode.DELAYED
    )


def test_retry_policy_overlay_chain_expect_later_layer_wins_per_field() -> None:
    """여러 겹을 덮으면 필드마다 나중 겹이 이긴다."""
    base = RetryPolicy(max_attempts=2, initial_interval=0.5)
    declared = RetryPolicy(mode=RetryMode.DELAYED, max_attempts=3)
    deployed = RetryPolicy(max_attempts=7)

    merged = base.overlay(declared).overlay(deployed)

    assert merged == RetryPolicy(
        max_attempts=7, initial_interval=0.5, mode=RetryMode.DELAYED
    )


def test_retry_policy_overlay_explicit_default_expect_default_applied() -> None:
    """기본값과 같은 값이라도 명시했으면 바탕 값을 덮는다."""
    base = RetryPolicy(mode=RetryMode.DELAYED)

    merged = base.overlay(RetryPolicy(mode=RetryMode.BLOCKING))

    assert merged.mode is RetryMode.BLOCKING


def test_retry_policy_declares_same_expect_explicit_fields_compared() -> None:
    """같은 값이어도 명시한 필드가 다르면 다른 선언이다."""
    mode_only = RetryPolicy(mode=RetryMode.DELAYED)

    assert mode_only.declares_same(RetryPolicy(mode=RetryMode.DELAYED))
    assert mode_only == RetryPolicy(mode=RetryMode.DELAYED, max_attempts=1)
    assert not mode_only.declares_same(
        RetryPolicy(mode=RetryMode.DELAYED, max_attempts=1)
    )
