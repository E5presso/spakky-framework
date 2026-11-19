"""Retry policy a subscriber applies to its failed deliveries.

The policy lives apart from `spakky.event.delivery` because the consumer
interfaces in `spakky.event.event_consumer` and the `@EventHandler` stereotype
take it as an argument, and `spakky.event.delivery` itself depends on those
interfaces.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


class RetryMode(StrEnum):
    """How a failed delivery waits for its next attempt."""

    BLOCKING = "blocking"
    """Keep the message in place; later messages wait, so order is preserved."""

    DELAYED = "delayed"
    """Set the message aside and continue; throughput is kept, order is not."""


class RetryPolicy(BaseModel):
    """Retry limits and spacing applied to each subscriber independently.

    Every field has a default, so a policy also records which fields were
    written explicitly (`model_fields_set`). `overlay` applies only those, which
    lets code declare the mode while deployment settings keep the attempt
    counts and intervals.
    """

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=1, ge=1)
    """Total delivery attempts including the first one."""

    initial_interval: float = Field(default=0.0, ge=0)
    """Seconds to wait before the second attempt."""

    multiplier: float = Field(default=2.0, ge=1)
    """Growth factor applied to the interval after every failed attempt."""

    max_interval: float = Field(default=60.0, ge=0)
    """Upper bound for the wait between two attempts, in seconds."""

    mode: RetryMode = RetryMode.BLOCKING
    """Whether a waiting retry blocks later messages of the same stream."""

    def delay_after(self, attempt: int) -> float:
        """Return the wait that follows a failed attempt.

        Args:
            attempt: 1-based number of the attempt that just failed.

        Returns:
            Seconds to wait before the next attempt.
        """
        delay = min(self.initial_interval, self.max_interval)
        for _ in range(attempt - 1):
            delay = min(delay * self.multiplier, self.max_interval)
        return delay

    def overlay(self, override: Self | None) -> Self:
        """Return this policy with the explicitly set fields of `override` applied.

        Args:
            override: Policy whose explicitly set fields win; None changes
                nothing.

        Returns:
            A policy that keeps every field `override` did not set explicitly.
        """
        if override is None:
            return self
        return self.model_copy(
            update=override.model_dump(include=override.model_fields_set)
        )

    def declares_same(self, other: Self) -> bool:
        """Report whether two policies set the same fields to the same values.

        Two policies that compare equal can still differ in what they set
        explicitly, and so overlay differently; this compares exactly that.
        """
        return self.model_dump(include=self.model_fields_set) == other.model_dump(
            include=other.model_fields_set
        )
