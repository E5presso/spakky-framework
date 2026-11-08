"""Plugin initialization entry point for spakky-agent."""

from spakky.core.application.application import SpakkyApplication

from spakky.agent.mailbox import InProcessAgentSignalMailbox
from spakky.agent.post_processor import AgentBootstrapValidationPostProcessor
from spakky.agent.runner_factory import AgentRunnerFactory


def initialize(app: SpakkyApplication) -> None:
    """Initialize spakky-agent core contracts.

    The package intentionally registers no persistence implementation; production
    repositories must arrive through feature contributions. It registers the
    default in-process live signal mailbox that repositories publish committed
    signals to and runners subscribe to.
    """
    app.add(InProcessAgentSignalMailbox)
    app.add(AgentRunnerFactory)
    app.add(AgentBootstrapValidationPostProcessor)
