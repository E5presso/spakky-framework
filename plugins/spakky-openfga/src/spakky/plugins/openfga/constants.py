"""Constants for the spakky-openfga plugin."""

OPENFGA_AUTH_PROVIDER_ID = "provider:spakky-openfga"
"""Stable auth provider id advertised by spakky-openfga."""

DEFAULT_OPENFGA_API_URL = "http://localhost:8080"
"""Default OpenFGA API URL for local development."""

DEFAULT_OPENFGA_USER_TYPE = "user"
"""Default OpenFGA object type used for AuthContext principals."""

DEFAULT_OPENFGA_TENANT_SEPARATOR = "/"
"""Separator used when tenant refs are embedded into OpenFGA object ids."""

SPAKKY_OPENFGA_CONFIG_ENV_PREFIX = "SPAKKY_OPENFGA_"
"""Environment variable prefix for OpenFGA provider settings."""
