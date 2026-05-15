"""Provider-neutral auth capability declarations."""

from enum import StrEnum


class AuthCapability(StrEnum):
    """Auth provider capabilities declared by feature contributions."""

    AUTHENTICATION = "AUTHENTICATION"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    PERMISSION_CHECK = "PERMISSION_CHECK"
    ROLE_CHECK = "ROLE_CHECK"
    SCOPE_CHECK = "SCOPE_CHECK"
    RELATION_CHECK = "RELATION_CHECK"
    SNAPSHOT_SIGN = "SNAPSHOT_SIGN"
    SNAPSHOT_VERIFY = "SNAPSHOT_VERIFY"
    PASSWORD_HASH = "PASSWORD_HASH"
    PASSWORD_VERIFY = "PASSWORD_VERIFY"
