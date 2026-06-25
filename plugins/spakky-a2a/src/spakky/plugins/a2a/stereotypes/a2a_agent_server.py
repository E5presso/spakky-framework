"""@A2AAgentServer marker for exposing an @Agent over the A2A protocol.

Unlike ``@GrpcController`` (which subclasses ``Controller`` and registers its own
Pod), this marker subclasses :class:`~spakky.core.pod.annotations.tag.Tag`: the
``@Agent`` decorator already registers the Pod, so this tag only records the A2A
transport metadata and stacks above ``@Agent`` on the same class.
"""

from dataclasses import dataclass

from spakky.core.pod.annotations.tag import Tag


@dataclass(eq=False)
class A2AAgentServer(Tag):
    """Marks an @Agent class to be served as an A2A protocol endpoint.

    Attributes:
        base_url: Transport endpoint advertised on the derived AgentCard.
        version: Semantic version advertised on the derived AgentCard.
    """

    base_url: str
    """Transport endpoint advertised on the derived AgentCard interface."""

    version: str
    """Semantic version advertised on the derived AgentCard."""
