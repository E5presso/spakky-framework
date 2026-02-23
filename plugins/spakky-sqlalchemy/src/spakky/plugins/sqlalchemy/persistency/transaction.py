from spakky.core.pod.annotations.pod import Pod
from spakky.data import AbstractAsyncTransaction, AbstractTransaction

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)


@Pod()
class Transaction(AbstractTransaction):
    __session_manager: SessionManager

    def __init__(
        self,
        config: SQLAlchemyConnectionConfig,
        session_manager: SessionManager,
    ) -> None:
        super().__init__(autocommit=config.autocommit)
        self.__session_manager = session_manager

    def initialize(self) -> None:
        self.__session_manager.open()

    def dispose(self) -> None:
        self.__session_manager.close()

    def commit(self) -> None:
        self.__session_manager.session.commit()

    def rollback(self) -> None:
        self.__session_manager.session.rollback()


@Pod()
class AsyncTransaction(AbstractAsyncTransaction):
    __session_manager: AsyncSessionManager

    def __init__(
        self,
        config: SQLAlchemyConnectionConfig,
        session_manager: AsyncSessionManager,
    ) -> None:
        super().__init__(autocommit=config.autocommit)
        self.__session_manager = session_manager

    async def initialize(self) -> None:
        await self.__session_manager.open()

    async def dispose(self) -> None:
        await self.__session_manager.close()

    async def commit(self) -> None:
        await self.__session_manager.session.commit()

    async def rollback(self) -> None:
        await self.__session_manager.session.rollback()
