from typing import TypeVar

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, scoped_session, sessionmaker

T = TypeVar("T")


@Pod()
class SessionManager(IApplicationContextAware):
    __application_context: IApplicationContext
    __engine: Engine
    __scoped_session: scoped_session[Session]

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context
        self.__scoped_session = scoped_session(
            session_factory=sessionmaker(
                bind=self.__engine,
                expire_on_commit=False,
            ),
            scopefunc=self.__application_context.get_context_id,
        )

    @property
    def session(self) -> Session:
        return self.__scoped_session()

    def open(self) -> None:
        self.__scoped_session()

    def close(self) -> None:
        self.__scoped_session().close()
        self.__scoped_session.remove()

    def __init__(self, config: SQLAlchemyConnectionConfig) -> None:
        self.__engine = create_engine(
            url=config.connection_string,
            echo=config.echo,
            echo_pool=config.echo_pool,
            pool_size=config.pool_size,
            pool_max_overflow=config.pool_max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=config.pool_pre_ping,
        )


@Pod()
class AsyncSessionManager(IApplicationContextAware):
    __application_context: IApplicationContext
    __engine: AsyncEngine
    __scoped_session: async_scoped_session[AsyncSession]

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context
        self.__scoped_session = async_scoped_session(
            session_factory=async_sessionmaker(
                bind=self.__engine,
                expire_on_commit=False,
            ),
            scopefunc=self.__application_context.get_context_id,
        )

    @property
    def session(self) -> AsyncSession:
        return self.__scoped_session()

    async def open(self) -> None:
        self.__scoped_session()

    async def close(self) -> None:
        await self.__scoped_session().close()
        await self.__scoped_session.remove()

    def __init__(self, config: SQLAlchemyConnectionConfig) -> None:
        self.__engine = create_async_engine(
            url=config.connection_string,
            echo=config.echo,
            echo_pool=config.echo_pool,
            pool_size=config.pool_size,
            pool_max_overflow=config.pool_max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=config.pool_pre_ping,
        )
