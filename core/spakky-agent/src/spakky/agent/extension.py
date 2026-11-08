"""Typed application values that travel with one agent run."""

from abc import ABC
from collections.abc import Sequence

from spakky.agent.error import AgentDefinitionError


class AgentRunExtension(ABC):
    """Base of a typed application value carried by a run and its model requests.

    An application subclasses it, usually as a frozen dataclass, instead of putting
    string keys into ``metadata``. The runner copies a run's extensions into every
    model request, and a model adapter reads one with ``request.extension(Type)``.
    A run carries at most one extension of each type.
    """


def validated_extensions(
    extensions: Sequence[AgentRunExtension],
) -> tuple[AgentRunExtension, ...]:
    """Snapshot extensions and reject values that are not unique typed extensions."""
    values = tuple(extensions)
    if any(not isinstance(value, AgentRunExtension) for value in values):
        raise AgentDefinitionError("Agent run extension is invalid")
    if len({type(value) for value in values}) != len(values):
        raise AgentDefinitionError("Agent run extension types must be unique")
    return values
