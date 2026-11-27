"""AgentRunner with synchronous SQLAlchemy agent repositories on PostgreSQL."""

from asyncio import create_task, sleep
from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass
from typing import cast, override

import pytest
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentRunner,
    AgentSignalKind,
    AgentState,
    AgentStatus,
    AgentYieldKind,
    IAgentModel,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    RecoveryStrategy,
    RunAgentInput,
)
from sqlalchemy import Engine, create_engine, delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Session

from spakky.plugins.sqlalchemy.agent.repository import (
    SqlAlchemyAgentEvidenceRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentStateRepository,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceOriginTable,
    AgentEvidenceTable,
    AgentSignalTable,
    AgentStateTable,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager

AGENT_TABLES = (
    AgentStateTable,
    AgentSignalTable,
    AgentEvidenceTable,
    AgentEvidenceOriginTable,
)

LOCK_TIMEOUT = "3s"
"""Upper bound of one row-lock wait; a blocked event loop fails here instead of hanging."""

LOCK_POLL_SECONDS = 0.01
"""Pause between checks for the runner's backend waiting on the row lock."""

STATE_ID = "lock-wait-run"


@dataclass(slots=True)
class _SessionManagerStub:
    session: Session


class _AnswerModel(IAgentModel):
    """Model that answers in one step."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="answer")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="answer"
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Agent(
    spec=AgentExecutionSpec(
        name="lock_wait_probe",
        accepted_signals=(AgentSignalKind.CANCEL,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class _DurableAgent:
    def __init__(
        self,
        model: IAgentModel,
        states: SqlAlchemyAgentStateRepository,
        signals: SqlAlchemyAgentSignalRepository,
        evidence: SqlAlchemyAgentEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence


@pytest.fixture(name="sync_engine")
def sync_engine_fixture(database_url: str) -> Generator[Engine, None, None]:
    """Synchronous engine with the agent tables and a bounded lock wait."""
    engine = create_engine(
        database_url, connect_args={"options": f"-c lock_timeout={LOCK_TIMEOUT}"}
    )
    for table in AGENT_TABLES:
        table.metadata.create_all(engine)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            for table in AGENT_TABLES:
                connection.execute(delete(table))
        engine.dispose()


@pytest.fixture(name="async_engine")
async def async_engine_fixture(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Asynchronous engine of the application-side transaction."""
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _hold_state_row_until_runner_waits(async_engine: AsyncEngine) -> None:
    """Lock the state row, then release it once another backend waits on it."""
    async with async_engine.begin() as connection:
        await connection.execute(
            text("SELECT id FROM spakky_agent_state WHERE id = :id FOR UPDATE"),
            {"id": STATE_ID},
        )
        while True:
            waiting = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            if waiting:
                return
            await sleep(LOCK_POLL_SECONDS)


@pytest.mark.asyncio
async def test_agent_runner_sync_repository_row_locked_by_async_transaction_expect_run_completes(
    sync_engine: Engine,
    async_engine: AsyncEngine,
) -> None:
    """같은 루프의 async 트랜잭션이 상태 행을 잠근 동안에도 실행기가 루프를 막지 않고 끝난다."""
    with Session(sync_engine) as seed:
        seed.add(
            AgentStateTable.from_domain(
                AgentState(
                    id=STATE_ID,
                    agent_type="lock_wait_probe",
                    status=AgentStatus.CREATED,
                )
            )
        )
        seed.commit()

    with Session(sync_engine, expire_on_commit=False) as session:
        manager = cast(SessionManager, _SessionManagerStub(session))
        runner = AgentRunner.for_agent_instance(
            _DurableAgent(
                _AnswerModel(),
                SqlAlchemyAgentStateRepository(manager),
                SqlAlchemyAgentSignalRepository(manager),
                SqlAlchemyAgentEvidenceRepository(manager),
            )
        )
        holder = create_task(_hold_state_row_until_runner_waits(async_engine))
        async with async_engine.connect() as probe:
            while not await probe.scalar(
                text(
                    "SELECT count(*) FROM pg_locks l JOIN pg_class c "
                    "ON c.oid = l.relation WHERE c.relname = 'spakky_agent_state' "
                    "AND l.mode = 'RowShareLock'"
                )
            ):
                await sleep(LOCK_POLL_SECONDS)

        items = [
            item
            async for item in runner.run(
                RunAgentInput(state_id=STATE_ID, instruction="go")
            )
        ]
        await holder
        session.commit()

    assert items[-1].kind is AgentYieldKind.FINAL
    with Session(sync_engine) as reader:
        stored = reader.get(AgentStateTable, STATE_ID)
        assert stored is not None
        assert stored.status == AgentStatus.COMPLETED.value
