"""Error strategy types for saga step failure handling.

This module defines the on_error strategies that control how a saga
responds to step failures:
- Compensate: trigger reverse compensation (default)
- Skip: ignore the failure and continue
- Retry: retry with backoff, then fall back to another strategy
"""

from typing import TypeAlias, Union

from spakky.core.common.mutability import immutable


def exponential(base: float = 1.0) -> float:
    """Create an exponential backoff base value.

    Args:
        base: The base value for exponential backoff calculation.

    Returns:
        The backoff base value.
    """
    return base


@immutable
class Compensate:
    """Trigger reverse compensation on step failure.

    This is the default error strategy. When a step fails,
    the saga engine will execute compensation in reverse order.
    """


@immutable
class Skip:
    """Skip the failed step and continue to the next one.

    Use this for non-critical steps where failure is acceptable.
    """


@immutable
class Retry:
    """Retry the failed step with exponential backoff.

    After exhausting max_attempts, falls back to the ``then`` strategy
    (defaults to Compensate).

    Attributes:
        max_attempts: Maximum number of retry attempts.
        backoff: Backoff base value for exponential delay (default: 1.0).
        then: Strategy to apply after all retries are exhausted.
    """

    max_attempts: int
    backoff: float = 1.0
    then: type[Compensate] | type[Skip] = Compensate


ErrorStrategy: TypeAlias = Union[Compensate, Skip, Retry]
"""Union type for all error strategies."""
