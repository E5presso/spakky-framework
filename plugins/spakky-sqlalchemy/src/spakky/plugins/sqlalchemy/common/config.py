from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.sqlalchemy.common.constants import (
    SPAKKY_SQLALCHEMY_CONFIG_ENV_PREFIX,
)


@Configuration()
class SQLAlchemyConnectionConfig(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_SQLALCHEMY_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    # --- Connection ---
    connection_string: str
    """SQLAlchemy database connection URL (e.g. postgresql+psycopg://user:pass@host/db)."""

    sync_connection_string: str | None = None
    """Optional synchronous driver URL for databases requiring separate drivers.

    For example sqlite+aiosqlite for async access and sqlite+pysqlite for sync.
    Omitted preserves the base connection_string for dual-mode drivers.
    """

    # --- Engine ---
    echo: bool = False
    """If True, the engine logs all SQL statements to the default logger."""
    echo_pool: bool = False
    """If True, the connection pool logs all checkout/checkin events."""

    # --- Connection Pool (QueuePool) Defaults ---
    DEFAULT_POOL_SIZE: ClassVar[int] = 5
    """Default number of connections in the pool."""
    DEFAULT_POOL_MAX_OVERFLOW: ClassVar[int] = 10
    """Default maximum overflow connections."""
    DEFAULT_POOL_TIMEOUT: ClassVar[float] = 30.0
    """Default seconds to wait when pool is exhausted."""
    DEFAULT_POOL_RECYCLE: ClassVar[int] = -1
    """Default connection recycle time (-1 = disabled)."""
    DEFAULT_POOL_PRE_PING: ClassVar[bool] = False
    """Default pre-ping setting."""

    # --- Connection Pool (QueuePool) ---
    pool_size: int = DEFAULT_POOL_SIZE
    """Number of connections to maintain persistently in the pool."""
    pool_max_overflow: int = DEFAULT_POOL_MAX_OVERFLOW
    """Maximum number of connections that can be opened beyond pool_size."""
    pool_timeout: float = DEFAULT_POOL_TIMEOUT
    """Seconds to wait before raising an error when the pool is exhausted."""
    pool_recycle: int = DEFAULT_POOL_RECYCLE
    """Recycle connections after this many seconds to prevent stale connections.
    Recommended when connecting through a proxy or firewall with idle timeouts."""
    pool_pre_ping: bool = DEFAULT_POOL_PRE_PING
    """If True, tests each connection for liveness before returning it from the pool.
    Prevents errors caused by connections dropped by the database server."""

    async_pool_mode: Literal["queue", "null"] = "queue"
    """Async pooling strategy. Use null when one engine serves multiple event loops.

    NullPool never shares a connection or asyncio queue between loops. Queue
    capacity settings are ignored in this mode; database/server limits still apply.
    The synchronous connection manager retains its ordinary pool.
    """

    # --- Session ---
    session_autoflush: bool = True
    """If True, the session automatically flushes pending changes before queries."""
    session_expire_on_commit: bool = True
    """If True, ORM objects are expired after each commit, forcing a reload on next access."""

    # --- Transaction ---
    autocommit: bool = True
    """If True, transactions are automatically committed after with statements. If False, transactions must be manually committed or rolled back."""

    def __init__(self) -> None:
        super().__init__()
