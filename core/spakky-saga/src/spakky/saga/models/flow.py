"""Flow types for saga step composition.

This module provides the core flow types used to build saga definitions:
- SagaStep: wraps an individual action (commit function)
- Transaction: a commit + compensate pair (created by >> operator)
- Parallel: a group of steps to execute concurrently (created by & operator)
- SagaFlow: the complete flow definition

Type aliases:
- ActionFn: callable for step commit actions
- CompensateFn: callable for step compensation actions
- FlowItem: union of all items that can appear in a saga_flow
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Generic, TypeAlias, TypeVar

from spakky.core.common.mutability import immutable
from spakky.saga.models.error_strategy import Compensate, ErrorStrategy
from spakky.saga.models.saga_data import AbstractSagaData

SagaDataT = TypeVar("SagaDataT", bound=AbstractSagaData)

ActionFn: TypeAlias = Callable[[SagaDataT], Awaitable[Any]]
"""Callable for step commit actions. May return updated SagaData or Any."""

CompensateFn: TypeAlias = Callable[[SagaDataT], Awaitable[None]]
"""Callable for step compensation actions. Must return None."""


@immutable
class SagaStep(Generic[SagaDataT]):
    """Wraps an individual action (commit function) for a saga step.

    Supports operators for composing saga flows:
    - ``>>`` creates a Transaction (step with compensate)
    - ``&`` creates a Parallel group
    - ``|`` sets an error strategy

    Attributes:
        action: The commit function to execute.
        on_error: Error strategy for this step (default: Compensate).
    """

    action: ActionFn[SagaDataT]
    on_error: ErrorStrategy = Compensate()

    def __rshift__(self, compensate: CompensateFn[SagaDataT]) -> Transaction[SagaDataT]:
        """Create a Transaction by pairing this step with a compensate function.

        Args:
            compensate: The compensation function to run on rollback.

        Returns:
            A Transaction containing this step's action and the compensate function.
        """
        return Transaction(
            action=self.action,
            compensate=compensate,
            on_error=self.on_error,
        )

    def __and__(
        self, other: SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT]
    ) -> Parallel[SagaDataT]:
        """Create a Parallel group by combining with another step.

        Args:
            other: Another step, transaction, or parallel group.

        Returns:
            A Parallel group containing both items.
        """
        left: list[SagaStep[SagaDataT] | Transaction[SagaDataT]] = [self]
        if isinstance(other, Parallel):
            return Parallel(items=tuple(left + list(other.items)))
        return Parallel(items=tuple(left + [other]))

    def __or__(self, strategy: ErrorStrategy) -> SagaStep[SagaDataT]:
        """Set an error strategy for this step.

        Args:
            strategy: The error strategy to apply.

        Returns:
            A new SagaStep with the error strategy set.
        """
        return SagaStep(action=self.action, on_error=strategy)


@immutable
class Transaction(Generic[SagaDataT]):
    """A commit + compensate pair for a saga step.

    Created by the ``>>`` operator on SagaStep.

    Attributes:
        action: The commit function to execute.
        compensate: The compensation function to run on rollback.
        on_error: Error strategy for this transaction (default: Compensate).
    """

    action: ActionFn[SagaDataT]
    compensate: CompensateFn[SagaDataT]
    on_error: ErrorStrategy = Compensate()

    def __and__(
        self, other: SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT]
    ) -> Parallel[SagaDataT]:
        """Create a Parallel group by combining with another step.

        Args:
            other: Another step, transaction, or parallel group.

        Returns:
            A Parallel group containing both items.
        """
        left: list[SagaStep[SagaDataT] | Transaction[SagaDataT]] = [self]
        if isinstance(other, Parallel):
            return Parallel(items=tuple(left + list(other.items)))
        return Parallel(items=tuple(left + [other]))

    def __or__(self, strategy: ErrorStrategy) -> Transaction[SagaDataT]:
        """Set an error strategy for this transaction.

        Args:
            strategy: The error strategy to apply.

        Returns:
            A new Transaction with the error strategy set.
        """
        return Transaction(
            action=self.action,
            compensate=self.compensate,
            on_error=strategy,
        )


@immutable
class Parallel(Generic[SagaDataT]):
    """A group of steps to execute concurrently.

    Created by the ``&`` operator on SagaStep/Transaction.

    Attributes:
        items: The steps or transactions to execute in parallel.
    """

    items: tuple[SagaStep[SagaDataT] | Transaction[SagaDataT], ...]

    def __and__(
        self, other: SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT]
    ) -> Parallel[SagaDataT]:
        """Extend this Parallel group with another step.

        Args:
            other: Another step, transaction, or parallel group.

        Returns:
            A new Parallel group containing all items.
        """
        if isinstance(other, Parallel):
            return Parallel(items=tuple(list(self.items) + list(other.items)))
        return Parallel(items=tuple(list(self.items) + [other]))


FlowItem: TypeAlias = (
    SagaStep[SagaDataT]
    | Transaction[SagaDataT]
    | Parallel[SagaDataT]
    | Callable[[SagaDataT], Awaitable[Any]]
)
"""Union of all items that can appear in a saga_flow."""


@immutable
class SagaFlow(Generic[SagaDataT]):
    """Complete flow definition for a saga.

    Contains an ordered sequence of flow items (steps, transactions,
    parallel groups, or callables) that define the saga's execution order.

    Attributes:
        items: The ordered sequence of flow items.
    """

    items: tuple[FlowItem[SagaDataT], ...]
