"""Unit tests for SQLAlchemy agent contribution initialization."""

from unittest.mock import MagicMock

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
from spakky.plugins.sqlalchemy.contributions.agent import initialize


def test_agent_contribution_expect_tables_and_repositories_registered() -> None:
    """agent contribution이 state/signal/evidence table과 repository를 등록한다."""
    app = MagicMock()

    initialize(app)

    added_types = [call.args[0] for call in app.add.call_args_list]
    assert added_types == [
        AgentStateTable,
        AgentSignalTable,
        AgentEvidenceTable,
        SqlAlchemyAgentStateRepository,
        SqlAlchemyAgentSignalRepository,
        SqlAlchemyAgentEvidenceRepository,
    ]
