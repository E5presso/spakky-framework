"""Plugin initialization entry point for spakky-agent."""

from spakky.core.application.application import SpakkyApplication

from spakky.agent.post_processor import AgentBootstrapValidationPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize spakky-agent core contracts.

    The package intentionally registers no persistence implementation; production
    repositories must arrive through feature contributions.
    """
    app.add(AgentBootstrapValidationPostProcessor)
