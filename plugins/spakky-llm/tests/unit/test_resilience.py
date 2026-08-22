"""Tests for deterministic profile-scoped resilience controls."""

from asyncio import CancelledError, Event, create_task
from typing import override

import pytest

from spakky.plugins.llm.error import (
    LlmCircuitOpenError,
    LlmConcurrencyLimitError,
    LlmFailureClass,
    LlmRateLimitError,
    LlmTimeoutError,
)
from spakky.plugins.llm.resilience import (
    ILLMClock,
    LlmCircuitBreakerPolicy,
    LlmCircuitState,
    LlmConcurrencyPolicy,
    LlmRateLimitPolicy,
    LlmResilienceController,
    LlmResiliencePolicy,
    LlmRetryPolicy,
    SystemLlmClock,
)


class RecordingClock(ILLMClock):
    """Deterministic clock that advances instead of blocking tests."""

    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []

    @override
    def now(self) -> float:
        return self.current

    @override
    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


class BlockingClock(ILLMClock):
    """Clock that exposes and externally releases one pending sleep."""

    def __init__(self) -> None:
        self.current = 0.0
        self.started = Event()
        self.release_sleep = Event()

    @override
    def now(self) -> float:
        return self.current

    @override
    async def sleep(self, seconds: float) -> None:
        self.started.set()
        await self.release_sleep.wait()
        self.current += seconds


def test_resilience_defaults_expect_every_control_disabled() -> None:
    """Spring-style defaults preserve one attempt and no ambient profile state."""
    policy = LlmResiliencePolicy()

    assert policy.retry.max_attempts == 1
    assert policy.retry.failure_classes == frozenset()
    assert policy.concurrency.max_in_flight is None
    assert policy.rate_limit.requests_per_period is None
    assert policy.circuit.failure_threshold is None


async def test_system_clock_expect_monotonic_now_and_nonblocking_zero_sleep() -> None:
    """Default clock is a concrete replaceable runtime implementation."""
    clock = SystemLlmClock()

    before = clock.now()
    await clock.sleep(0.0)
    after = clock.now()

    assert after >= before


async def test_retry_delay_expect_retry_after_precedes_backoff() -> None:
    """Typed Retry-After is authoritative over deterministic exponential backoff."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmRetryPolicy(
        max_attempts=3,
        backoff_seconds=2.0,
        max_backoff_seconds=10.0,
        failure_classes=frozenset({LlmFailureClass.RATE_LIMIT}),
    )

    delay = await controller.retry_delay(
        policy,
        1,
        LlmRateLimitError(retry_after_seconds=7.5),
    )
    backoff = await controller.retry_delay(policy, 2, LlmTimeoutError())

    assert delay == 7.5
    assert backoff == 4.0
    assert clock.sleeps == [7.5, 4.0]
    assert policy.delay_for(0, LlmTimeoutError()) == 0.0


async def test_concurrency_gate_expect_profile_local_rejection_and_release() -> None:
    """One profile's full semaphore rejects excess work and releases deterministically."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy(
        concurrency=LlmConcurrencyPolicy(max_in_flight=1),
    )
    first = await controller.acquire("profile-a", policy)

    with pytest.raises(LlmConcurrencyLimitError):
        await controller.acquire("profile-a", policy)

    other = await controller.acquire("profile-b", policy)
    await controller.release(first)
    again = await controller.acquire("profile-a", policy)
    await controller.release(other)
    await controller.release(again)
    await controller.release(again)


async def test_concurrency_queue_timeout_expect_typed_failure() -> None:
    """A bounded positive queue timeout cannot leak asyncio TimeoutError."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy(
        concurrency=LlmConcurrencyPolicy(
            max_in_flight=1,
            queue_timeout_seconds=0.001,
        )
    )
    first = await controller.acquire("profile-a", policy)

    with pytest.raises(LlmConcurrencyLimitError):
        await controller.acquire("profile-a", policy)

    await controller.release(first)


async def test_rate_gate_expect_spacing_with_injected_clock() -> None:
    """Profile pacing waits through the injected sleeper and never global state."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
            max_wait_seconds=10.0,
        )
    )

    first = await controller.acquire("profile-a", policy)
    await controller.release(first)
    second = await controller.acquire("profile-a", policy)
    await controller.release(second)

    assert clock.sleeps == [10.0]


async def test_rate_gate_wait_budget_expect_typed_retry_after() -> None:
    """A wait beyond the profile budget becomes a typed local rate-limit failure."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy(
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.release(first)

    with pytest.raises(LlmRateLimitError) as raised:
        await controller.acquire("profile-a", policy)

    assert raised.value.retry_after_seconds == 10.0


async def test_circuit_expect_open_half_open_and_success_reset() -> None:
    """Counted failure opens one profile, then one successful probe closes it."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            recovery_timeout_seconds=5.0,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(
        first,
        policy.circuit,
        LlmFailureClass.TIMEOUT,
    )
    await controller.release(first)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN
    with pytest.raises(LlmCircuitOpenError) as raised:
        await controller.acquire("profile-a", policy)
    assert raised.value.retry_after_seconds == 5.0

    await clock.sleep(5.0)
    probe = await controller.acquire("profile-a", policy)
    assert probe.circuit_state is LlmCircuitState.HALF_OPEN
    with pytest.raises(LlmCircuitOpenError):
        await controller.acquire("profile-a", policy)
    await controller.record_success(probe, policy.circuit)
    await controller.release(probe)

    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED


async def test_half_open_counted_failure_expect_reopens_circuit() -> None:
    """A failed half-open probe deterministically restarts the recovery timeout."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(circuit=LlmCircuitBreakerPolicy(failure_threshold=1))
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    probe = await controller.acquire("profile-a", policy)

    await controller.record_failure(probe, policy.circuit, LlmFailureClass.TRANSPORT)
    await controller.release(probe)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN


async def test_half_open_late_success_cannot_close_newly_reopened_epoch() -> None:
    """A sibling success from an obsolete probe generation cannot win the race."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            half_open_max_attempts=2,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    failed_probe = await controller.acquire("profile-a", policy)
    late_success = await controller.acquire("profile-a", policy)

    await controller.record_failure(
        failed_probe,
        policy.circuit,
        LlmFailureClass.TIMEOUT,
    )
    await controller.record_success(late_success, policy.circuit)
    await controller.release(failed_probe)
    await controller.release(late_success)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN


async def test_half_open_early_success_waits_for_late_counted_failure() -> None:
    """A first sibling success cannot close the cohort before a reserved probe fails."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            half_open_max_attempts=2,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    early_success = await controller.acquire("profile-a", policy)
    late_failure = await controller.acquire("profile-a", policy)

    await controller.record_success(early_success, policy.circuit)
    assert controller.circuit_state("profile-a") is LlmCircuitState.HALF_OPEN
    await controller.record_failure(
        late_failure,
        policy.circuit,
        LlmFailureClass.TIMEOUT,
    )
    await controller.release(early_success)
    await controller.release(late_failure)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN


async def test_half_open_uncounted_failure_expect_closes_without_poisoning() -> None:
    """Refusal-like failures prove reachability and do not poison the circuit."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(circuit=LlmCircuitBreakerPolicy(failure_threshold=1))
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    probe = await controller.acquire("profile-a", policy)

    await controller.record_failure(probe, policy.circuit, LlmFailureClass.REFUSAL)
    await controller.release(probe)

    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED


async def test_half_open_uncounted_result_waits_for_reserved_sibling() -> None:
    """An uncounted result cannot close the circuit while another probe is active."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            half_open_max_attempts=2,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    refusal = await controller.acquire("profile-a", policy)
    success = await controller.acquire("profile-a", policy)

    await controller.record_failure(refusal, policy.circuit, LlmFailureClass.REFUSAL)
    assert controller.circuit_state("profile-a") is LlmCircuitState.HALF_OPEN
    await controller.record_success(success, policy.circuit)
    await controller.release(refusal)
    await controller.release(success)

    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED


async def test_disabled_circuit_success_and_failure_expect_no_state_transition() -> (
    None
):
    """Disabled circuit records neither successful nor failed provider state."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy()
    success = await controller.acquire("profile-a", policy)
    await controller.record_success(success, policy.circuit)
    await controller.release(success)
    failure = await controller.acquire("profile-a", policy)
    await controller.record_failure(failure, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(failure)

    assert controller.circuit_state("profile-a") is LlmCircuitState.DISABLED
    assert controller.circuit_state("missing") is LlmCircuitState.DISABLED


async def test_circuit_below_threshold_expect_remains_closed() -> None:
    """A counted failure below threshold retains the closed state."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy(circuit=LlmCircuitBreakerPolicy(failure_threshold=2))
    lease = await controller.acquire("profile-a", policy)

    await controller.record_failure(lease, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(lease)

    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED


async def test_closed_circuit_success_and_uncounted_failure_expect_reset() -> None:
    """Closed success and uncounted failure cover non-probe reset semantics."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy(circuit=LlmCircuitBreakerPolicy(failure_threshold=2))
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    refusal = await controller.acquire("profile-a", policy)
    await controller.record_failure(refusal, policy.circuit, LlmFailureClass.REFUSAL)
    await controller.release(refusal)
    success = await controller.acquire("profile-a", policy)
    await controller.record_success(success, policy.circuit)
    await controller.release(success)

    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED


async def test_abandoned_half_open_probe_expect_reservation_released() -> None:
    """Cancellation-like release frees the half-open probe without changing state."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(circuit=LlmCircuitBreakerPolicy(failure_threshold=1))
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    abandoned = await controller.acquire("profile-a", policy)

    await controller.release(abandoned)
    replacement = await controller.acquire("profile-a", policy)
    await controller.record_success(replacement, policy.circuit)
    await controller.release(replacement)

    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED


async def test_stale_abandoned_probe_cannot_mutate_new_circuit_epoch() -> None:
    """An abandoned sibling from a reopened cohort cannot decrement the new epoch."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            half_open_max_attempts=2,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    failure = await controller.acquire("profile-a", policy)
    abandoned = await controller.acquire("profile-a", policy)

    await controller.record_failure(failure, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(abandoned)
    await controller.release(failure)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN


async def test_stale_gate_abandonment_cannot_mutate_new_circuit_epoch() -> None:
    """Gate cleanup from an obsolete reservation leaves the reopened epoch intact."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            half_open_max_attempts=2,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    stale = await controller.acquire("profile-a", policy)
    failure = await controller.acquire("profile-a", policy)
    await controller.record_failure(failure, policy.circuit, LlmFailureClass.TIMEOUT)

    await controller._abandon_circuit_reservation(
        stale.state,
        stale.circuit_state,
        stale.circuit_epoch,
    )
    await controller.release(stale)
    await controller.release(failure)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN


async def test_stale_failure_cannot_mutate_new_circuit_epoch() -> None:
    """A late counted failure is ignored after a sibling already reopened the cohort."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            half_open_max_attempts=2,
        )
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)
    first_failure = await controller.acquire("profile-a", policy)
    stale_failure = await controller.acquire("profile-a", policy)

    await controller.record_failure(
        first_failure,
        policy.circuit,
        LlmFailureClass.TIMEOUT,
    )
    await controller.record_failure(
        stale_failure,
        policy.circuit,
        LlmFailureClass.TIMEOUT,
    )
    await controller.release(first_failure)
    await controller.release(stale_failure)

    assert controller.circuit_state("profile-a") is LlmCircuitState.OPEN


async def test_corrupted_open_state_expect_typed_circuit_error() -> None:
    """Impossible missing open timestamp remains inside the typed error boundary."""
    controller = LlmResilienceController(RecordingClock())
    policy = LlmResiliencePolicy(circuit=LlmCircuitBreakerPolicy(failure_threshold=1))
    lease = await controller.acquire("profile-a", policy)
    lease.state.circuit_state = LlmCircuitState.OPEN
    lease.state.opened_at = None
    await controller.release(lease)

    with pytest.raises(LlmCircuitOpenError):
        await controller.acquire("profile-a", policy)


async def test_half_open_rate_rejection_expect_probe_reservation_abandoned() -> None:
    """A local rate rejection after half-open admission does not leak the probe slot."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=100.0,
        ),
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            recovery_timeout_seconds=30.0,
        ),
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    await clock.sleep(30.0)

    with pytest.raises(LlmRateLimitError):
        await controller.acquire("profile-a", policy)

    clock.current = 100.0
    probe = await controller.acquire("profile-a", policy)
    await controller.record_success(probe, policy.circuit)
    await controller.release(probe)


async def test_half_open_cancelled_rate_wait_releases_probe_and_concurrency() -> None:
    """Task cancellation during pacing cannot strand a half-open reservation."""
    clock = BlockingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        concurrency=LlmConcurrencyPolicy(max_in_flight=1),
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=100.0,
            max_wait_seconds=100.0,
        ),
        circuit=LlmCircuitBreakerPolicy(
            failure_threshold=1,
            recovery_timeout_seconds=30.0,
        ),
    )
    first = await controller.acquire("profile-a", policy)
    await controller.record_failure(first, policy.circuit, LlmFailureClass.TIMEOUT)
    await controller.release(first)
    clock.current = 30.0
    waiting = create_task(controller.acquire("profile-a", policy))
    await clock.started.wait()

    waiting.cancel()
    with pytest.raises(CancelledError):
        await waiting

    clock.current = 100.0
    clock.release_sleep.set()
    replacement = await controller.acquire("profile-a", policy)
    await controller.record_success(replacement, policy.circuit)
    await controller.release(replacement)
    assert controller.circuit_state("profile-a") is LlmCircuitState.CLOSED
    assert clock.current == 100.0


async def test_concurrency_rejection_does_not_consume_rate_capacity() -> None:
    """A request rejected before admission cannot reserve a future rate slot."""
    clock = RecordingClock()
    controller = LlmResilienceController(clock)
    policy = LlmResiliencePolicy(
        concurrency=LlmConcurrencyPolicy(max_in_flight=1),
        rate_limit=LlmRateLimitPolicy(
            requests_per_period=1,
            period_seconds=10.0,
            max_wait_seconds=10.0,
        ),
    )
    first = await controller.acquire("profile-a", policy)

    with pytest.raises(LlmConcurrencyLimitError):
        await controller.acquire("profile-a", policy)
    assert clock.current == 0.0
    assert clock.sleeps == []

    await controller.release(first)
    admitted = await controller.acquire("profile-a", policy)
    await controller.release(admitted)
    assert clock.current == 10.0
    assert clock.sleeps == [10.0]
