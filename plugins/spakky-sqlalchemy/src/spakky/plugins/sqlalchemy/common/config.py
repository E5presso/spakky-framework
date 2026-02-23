from typing import ClassVar

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

    # --- Engine ---
    echo: bool = False
    """If True, the engine logs all SQL statements to the default logger."""
    echo_pool: bool = False
    """If True, the connection pool logs all checkout/checkin events."""

    # --- Connection Pool (QueuePool) ---
    # These settings are optional because some databases (e.g., SQLite) use
    # different pool implementations that don't support these parameters.
    pool_size: int | None = None
    """Number of connections to maintain persistently in the pool.
    None uses SQLAlchemy default (5). Not applicable for SQLite."""
    pool_max_overflow: int | None = None
    """Maximum number of connections that can be opened beyond pool_size.
    None uses SQLAlchemy default (10). Not applicable for SQLite."""
    pool_timeout: float | None = None
    """Seconds to wait before raising an error when the pool is exhausted.
    None uses SQLAlchemy default (30). Not applicable for SQLite."""
    pool_recycle: int | None = None
    """Recycle connections after this many seconds to prevent stale connections.
    Recommended when connecting through a proxy or firewall with idle timeouts.
    None uses SQLAlchemy default (-1, disabled)."""
    pool_pre_ping: bool | None = None
    """If True, tests each connection for liveness before returning it from the pool.
    Prevents errors caused by connections dropped by the database server.
    None uses SQLAlchemy default (False)."""

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
