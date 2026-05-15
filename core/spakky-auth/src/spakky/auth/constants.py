"""Stable keys and defaults for provider-neutral auth contracts."""

AUTH_CONTEXT_CONTEXT_KEY = "spakky.auth.context"
"""ApplicationContext context value key for the current AuthContext."""

AUTH_CONTEXT_SNAPSHOT_METADATA_KEY = "spakky.auth.context_snapshot"
"""Transport metadata key for signed AuthContextSnapshot propagation."""

AUTH_CONTEXT_SNAPSHOT_HEADER_KEY = "x-spakky-auth-context-snapshot"
"""HTTP/gRPC-style header key for signed AuthContextSnapshot propagation."""

AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION = 1
"""Current signed AuthContextSnapshot envelope schema version."""

DEFAULT_AUTH_CLOCK_SKEW_SECONDS = 60
"""Default tolerated clock skew for AuthContextSnapshot validation."""
