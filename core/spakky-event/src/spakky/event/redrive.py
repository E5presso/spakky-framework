"""Redrive contract: hand dead letters back to the subscriber they failed for."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.subscription import SubscriberName


class RedriveResult(BaseModel):
    """How many dead letters one redrive call settled."""

    model_config = ConfigDict(frozen=True)

    succeeded: int
    """Dead letters whose failed handlers all completed; they are removed."""

    failed: int
    """Dead letters that failed again; they stay in the dead-letter destination."""


class IEventRedriver(ABC):
    """Synchronous redrive of one subscriber's dead letters.

    A redrive reaches only the subscriber that dead-lettered the message, and
    runs only the handlers recorded as failed. Other subscribers of the same
    event never see the message again.
    """

    @abstractmethod
    def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Deliver dead letters of `subscriber` for `event` to their failed handlers.

        Args:
            event: Event type whose dead letters are redriven.
            subscriber: Subscriber owning the dead letters; None is unnamed.
            limit: Most dead letters to take in this call; None takes all
                currently stored.

        Returns:
            Counts of dead letters that completed and that failed again.
        """
        ...


class IAsyncEventRedriver(ABC):
    """Asynchronous redrive of one subscriber's dead letters.

    Follows the same contract as `IEventRedriver`.
    """

    @abstractmethod
    async def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Deliver dead letters of `subscriber` for `event` to their failed handlers.

        Args:
            event: Event type whose dead letters are redriven.
            subscriber: Subscriber owning the dead letters; None is unnamed.
            limit: Most dead letters to take in this call; None takes all
                currently stored.

        Returns:
            Counts of dead letters that completed and that failed again.
        """
        ...
