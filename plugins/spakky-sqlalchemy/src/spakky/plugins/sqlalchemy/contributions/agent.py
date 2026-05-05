"""SQLAlchemy contribution for the spakky-agent feature."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.sqlalchemy.agent.repository import (
    SqlAlchemyAgentEvidenceRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentStateRepository,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceTable,
    AgentSignalTable,
    AgentStateTable,
)


def initialize(app: SpakkyApplication) -> None:
    """Register SQLAlchemy-backed agent persistence infrastructure."""
    app.add(AgentStateTable)
    app.add(AgentSignalTable)
    app.add(AgentEvidenceTable)
    app.add(SqlAlchemyAgentStateRepository)
    app.add(SqlAlchemyAgentSignalRepository)
    app.add(SqlAlchemyAgentEvidenceRepository)
