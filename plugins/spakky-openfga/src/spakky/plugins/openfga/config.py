"""Configuration for OpenFGA relationship checks."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.openfga.constants import (
    DEFAULT_OPENFGA_API_URL,
    DEFAULT_OPENFGA_TENANT_SEPARATOR,
    DEFAULT_OPENFGA_USER_TYPE,
    SPAKKY_OPENFGA_CONFIG_ENV_PREFIX,
)


@Configuration()
class OpenFgaConfig(BaseSettings):
    """Runtime config for OpenFGA check-only authorization."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_OPENFGA_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    api_url: str = DEFAULT_OPENFGA_API_URL
    """OpenFGA API URL."""

    store_id: str = ""
    """OpenFGA store id used for check requests."""

    authorization_model_id: str | None = None
    """Optional authorization model id for check requests."""

    principal_type: str = DEFAULT_OPENFGA_USER_TYPE
    """OpenFGA object type prepended to principal ids without a type prefix."""

    tenant_separator: str = DEFAULT_OPENFGA_TENANT_SEPARATOR
    """Separator used to embed tenant refs into checked object ids."""

    include_tenant_in_object: bool = True
    """Whether tenant refs are prefixed into OpenFGA object strings."""

    relation_check_available: bool = True
    """Whether OpenFGA relationship checking is available at runtime."""

    def __init__(self) -> None:
        super().__init__()
