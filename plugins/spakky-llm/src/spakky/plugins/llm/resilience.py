"""Profile-scoped retry, concurrency, rate, and circuit-breaker policies."""

from abc import ABC, abstractmethod
from asyncio import Lock, Semaphore, TimeoutError as AsyncTimeoutError, sleep, wait_for
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import override

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from spakky.plugins.llm.error import (
    AbstractLlmError,
    LlmCircuitOpenError,
    LlmConcurrencyLimitError,
    LlmFailureClass,
    LlmRateLimitError,
)


class LlmRetryPolicy(BaseModel):
    """Bounded orchestration retry policy; one attempt means disabled."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=1, ge=1, le=10)
    backoff_seconds: float = Field(default=0.0, ge=0)
    max_backoff_seconds: float = Field(default=60.0, ge=0)
    failure_classes: frozenset[LlmFailureClass] = frozenset()

    @model_validator(mode="after")
    def _validate_retry_policy(self) -> "LlmRetryPolicy":
        if self.max_attempts > 1 and len(self.failure_classes) == 0:
            raise PydanticCustomError(
                "llm_retry_failures",
                "Enabled LLM retry requires explicit failure classes",
            )
        if self.max_backoff_seconds < self.backoff_seconds:
            raise PydanticCustomError(
                "llm_retry_backoff",
                "LLM retry max backoff cannot be below its base backoff",
            )
        return self

    def delay_for(self, retry_count: int, error: AbstractLlmError) -> float:
        """Return Retry-After or the bounded deterministic exponential delay."""
        if error.retry_after_seconds is not None:
            return error.retry_after_seconds
        if retry_count <= 0 or self.backoff_seconds == 0:
            return 0.0
        delay = self.backoff_seconds * (2 ** (retry_count - 1))
        return min(delay, self.max_backoff_seconds)


class LlmConcurrencyPolicy(BaseModel):
    """Optional bounded in-flight gate for one connection profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_in_flight: int | None = Field(default=None, ge=1)
    queue_timeout_seconds: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _validate_concurrency_policy(self) -> "LlmConcurrencyPolicy":
        if self.max_in_flight is None and self.queue_timeout_seconds != 0:
            raise PydanticCustomError(
                "llm_concurrency_disabled",
                "Concurrency queue timeout requires max_in_flight",
            )
        return self


class LlmRateLimitPolicy(BaseModel):
    """Optional deterministic request pacing for one connection profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requests_per_period: int | None = Field(default=None, ge=1)
    period_seconds: float = Field(default=1.0, gt=0)
    max_wait_seconds: float = Field(default=0.0, ge=0)


class LlmCircuitBreakerPolicy(BaseModel):
    """Optional consecutive-failure circuit for one connection profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    failure_threshold: int | None = Field(default=None, ge=1)
    recovery_timeout_seconds: float = Field(default=30.0, gt=0)
    half_open_max_attempts: int = Field(default=1, ge=1)
    failure_classes: frozenset[LlmFailureClass] = frozenset(
        {
            LlmFailureClass.TIMEOUT,
            LlmFailureClass.TRANSPORT,
            LlmFailureClass.PROVIDER_UNAVAILABLE,
        }
    )

    @model_validator(mode="after")
    def _validate_circuit_policy(self) -> "LlmCircuitBreakerPolicy":
        if self.failure_threshold is not None and len(self.failure_classes) == 0:
            raise PydanticCustomError(
                "llm_circuit_failures",
                "Enabled LLM circuit requires explicit failure classes",
            )
        return self


class LlmResiliencePolicy(BaseModel):
    """Spring-style profile policy with every behavior disabled by default."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retry: LlmRetryPolicy = Field(default_factory=LlmRetryPolicy)
    concurrency: LlmConcurrencyPolicy = Field(default_factory=LlmConcurrencyPolicy)
    rate_limit: LlmRateLimitPolicy = Field(default_factory=LlmRateLimitPolicy)
    circuit: LlmCircuitBreakerPolicy = Field(default_factory=LlmCircuitBreakerPolicy)


class LlmCircuitState(StrEnum):
    """Observable state of one profile-scoped circuit."""

    DISABLED = "disabled"
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ILLMClock(ABC):
    """Replaceable monotonic clock and sleeper for deterministic policies."""

    @abstractmethod
    def now(self) -> float:
        """Return monotonic seconds."""
        ...

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Advance or wait for the requested duration."""
        ...


class SystemLlmClock(ILLMClock):
    """Default runtime clock backed by the event loop and monotonic time."""

    @override
    def now(self) -> float:
        return monotonic()

    @override
    async def sleep(self, seconds: float) -> None:
        await sleep(seconds)


@dataclass(slots=True)
class _ProfileState:
    """Mutable state owned by one model instance and one profile key."""

    semaphore: Semaphore | None
    rate_lock: Lock = field(default_factory=Lock)
    circuit_lock: Lock = field(default_factory=Lock)
    next_request_at: float = 0.0
    circuit_state: LlmCircuitState = LlmCircuitState.DISABLED
    consecutive_failures: int = 0
    opened_at: float | None = None
    half_open_in_flight: int = 0
    circuit_epoch: int = 0


@dataclass(slots=True)
class LlmAttemptLease:
    """One admitted profile attempt whose resources must be released exactly once."""

    profile_name: str
    state: _ProfileState
    circuit_state: LlmCircuitState
    circuit_epoch: int
    semaphore_acquired: bool
    circuit_finished: bool = False
    released: bool = False


class LlmResilienceController:
    """Coordinate independent retry gates and circuit state per profile."""

    __clock: ILLMClock
    __states: dict[str, _ProfileState]

    def __init__(self, clock: ILLMClock | None = None) -> None:
        self.__clock = clock if clock is not None else SystemLlmClock()
        self.__states = {}

    async def acquire(
        self,
        profile_name: str,
        policy: LlmResiliencePolicy,
    ) -> LlmAttemptLease:
        """Apply circuit, rate, and concurrency gates before provider execution."""
        state = self._state(profile_name, policy)
        circuit_state, circuit_epoch = await self._reserve_circuit(
            state,
            policy.circuit,
        )
        semaphore_acquired = False
        try:
            semaphore_acquired = await self._acquire_concurrency(
                state,
                policy.concurrency,
            )
            await self._apply_rate_limit(state, policy.rate_limit)
        except BaseException:
            if semaphore_acquired and state.semaphore is not None:
                state.semaphore.release()
            await self._abandon_circuit_reservation(
                state,
                circuit_state,
                circuit_epoch,
            )
            raise
        return LlmAttemptLease(
            profile_name=profile_name,
            state=state,
            circuit_state=circuit_state,
            circuit_epoch=circuit_epoch,
            semaphore_acquired=semaphore_acquired,
        )

    async def record_success(
        self,
        lease: LlmAttemptLease,
        policy: LlmCircuitBreakerPolicy,
    ) -> None:
        """Close an enabled circuit after a successful provider attempt."""
        if policy.failure_threshold is None:
            lease.circuit_finished = True
            return
        async with lease.state.circuit_lock:
            if lease.circuit_epoch != lease.state.circuit_epoch:
                lease.circuit_finished = True
                return
            if lease.circuit_state is LlmCircuitState.HALF_OPEN:
                lease.state.half_open_in_flight -= 1
                if lease.state.half_open_in_flight == 0:
                    self._close_circuit(lease.state, advance_epoch=True)
            else:
                self._close_circuit(lease.state, advance_epoch=False)
            lease.circuit_finished = True

    async def record_failure(
        self,
        lease: LlmAttemptLease,
        policy: LlmCircuitBreakerPolicy,
        failure_class: LlmFailureClass,
    ) -> None:
        """Advance only explicitly counted failures through circuit state."""
        if policy.failure_threshold is None:
            lease.circuit_finished = True
            return
        async with lease.state.circuit_lock:
            if lease.circuit_epoch != lease.state.circuit_epoch:
                lease.circuit_finished = True
                return
            if lease.circuit_state is LlmCircuitState.HALF_OPEN:
                lease.state.half_open_in_flight -= 1
            if failure_class not in policy.failure_classes:
                if lease.circuit_state is LlmCircuitState.HALF_OPEN:
                    if lease.state.half_open_in_flight == 0:
                        self._close_circuit(lease.state, advance_epoch=True)
                else:
                    self._close_circuit(lease.state, advance_epoch=False)
                lease.circuit_finished = True
                return
            if lease.circuit_state is LlmCircuitState.HALF_OPEN:
                self._open_circuit(lease.state)
                lease.circuit_finished = True
                return
            lease.state.consecutive_failures += 1
            if lease.state.consecutive_failures >= policy.failure_threshold:
                self._open_circuit(lease.state)
            lease.circuit_finished = True

    async def release(self, lease: LlmAttemptLease) -> None:
        """Release concurrency and abandoned half-open reservations once."""
        if lease.released:
            return
        if (
            not lease.circuit_finished
            and lease.circuit_state is LlmCircuitState.HALF_OPEN
        ):
            async with lease.state.circuit_lock:
                if lease.circuit_epoch == lease.state.circuit_epoch:
                    lease.state.half_open_in_flight -= 1
        if lease.semaphore_acquired and lease.state.semaphore is not None:
            lease.state.semaphore.release()
        lease.released = True

    async def retry_delay(
        self,
        policy: LlmRetryPolicy,
        retry_count: int,
        error: AbstractLlmError,
    ) -> float:
        """Sleep for one deterministic retry delay and return the evidence value."""
        delay = policy.delay_for(retry_count, error)
        if delay > 0:
            await self.__clock.sleep(delay)
        return delay

    def circuit_state(self, profile_name: str) -> LlmCircuitState:
        """Return an existing profile circuit state without creating global state."""
        state = self.__states.get(profile_name)
        return state.circuit_state if state is not None else LlmCircuitState.DISABLED

    def _state(
        self,
        profile_name: str,
        policy: LlmResiliencePolicy,
    ) -> _ProfileState:
        state = self.__states.get(profile_name)
        if state is not None:
            return state
        circuit_state = (
            LlmCircuitState.CLOSED
            if policy.circuit.failure_threshold is not None
            else LlmCircuitState.DISABLED
        )
        state = _ProfileState(
            semaphore=(
                Semaphore(policy.concurrency.max_in_flight)
                if policy.concurrency.max_in_flight is not None
                else None
            ),
            circuit_state=circuit_state,
        )
        self.__states[profile_name] = state
        return state

    async def _reserve_circuit(
        self,
        state: _ProfileState,
        policy: LlmCircuitBreakerPolicy,
    ) -> tuple[LlmCircuitState, int]:
        if policy.failure_threshold is None:
            return LlmCircuitState.DISABLED, state.circuit_epoch
        async with state.circuit_lock:
            if state.circuit_state is LlmCircuitState.OPEN:
                opened_at = state.opened_at
                if opened_at is None:
                    raise LlmCircuitOpenError
                retry_after = (
                    opened_at + policy.recovery_timeout_seconds - self.__clock.now()
                )
                if retry_after > 0:
                    raise LlmCircuitOpenError(retry_after_seconds=retry_after)
                state.circuit_state = LlmCircuitState.HALF_OPEN
                state.half_open_in_flight = 0
            if state.circuit_state is LlmCircuitState.HALF_OPEN:
                if state.half_open_in_flight >= policy.half_open_max_attempts:
                    raise LlmCircuitOpenError(retry_after_seconds=0.0)
                state.half_open_in_flight += 1
                return LlmCircuitState.HALF_OPEN, state.circuit_epoch
            return LlmCircuitState.CLOSED, state.circuit_epoch

    async def _apply_rate_limit(
        self,
        state: _ProfileState,
        policy: LlmRateLimitPolicy,
    ) -> None:
        requests = policy.requests_per_period
        if requests is None:
            return
        deadline = self.__clock.now() + policy.max_wait_seconds
        while True:
            async with state.rate_lock:
                now = self.__clock.now()
                delay = max(0.0, state.next_request_at - now)
                if delay == 0:
                    state.next_request_at = now + policy.period_seconds / requests
                    return
                if now + delay > deadline:
                    raise LlmRateLimitError(retry_after_seconds=delay)
            await self.__clock.sleep(delay)

    async def _acquire_concurrency(
        self,
        state: _ProfileState,
        policy: LlmConcurrencyPolicy,
    ) -> bool:
        semaphore = state.semaphore
        if semaphore is None:
            return False
        if policy.queue_timeout_seconds == 0:
            if semaphore.locked():
                raise LlmConcurrencyLimitError
            await semaphore.acquire()
            return True
        try:
            await wait_for(semaphore.acquire(), timeout=policy.queue_timeout_seconds)
        except AsyncTimeoutError as error:
            raise LlmConcurrencyLimitError from error
        return True

    async def _abandon_circuit_reservation(
        self,
        state: _ProfileState,
        circuit_state: LlmCircuitState,
        circuit_epoch: int,
    ) -> None:
        if circuit_state is not LlmCircuitState.HALF_OPEN:
            return
        async with state.circuit_lock:
            if circuit_epoch == state.circuit_epoch:
                state.half_open_in_flight -= 1

    def _open_circuit(self, state: _ProfileState) -> None:
        state.circuit_state = LlmCircuitState.OPEN
        state.opened_at = self.__clock.now()
        state.half_open_in_flight = 0
        state.circuit_epoch += 1

    @staticmethod
    def _close_circuit(state: _ProfileState, *, advance_epoch: bool) -> None:
        state.circuit_state = LlmCircuitState.CLOSED
        state.consecutive_failures = 0
        state.opened_at = None
        if advance_epoch:
            state.circuit_epoch += 1
