"""Plugin initialization entry point for spakky-auth."""

from spakky.auth.aspects import AsyncAuthorizationAspect, AuthorizationAspect
from spakky.auth.startup import (
    AuthCapabilityStartupValidationService,
    auth_snapshot_propagation_config,
)
from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-auth package.

    Registers auth AOP enforcement components and feature-local startup
    capability validation. Provider implementations and boundary AuthContext
    seeding are added by downstream auth issues.
    """
    app.add(auth_snapshot_propagation_config)
    app.add(AuthCapabilityStartupValidationService)
    app.add(AuthorizationAspect)
    app.add(AsyncAuthorizationAspect)
