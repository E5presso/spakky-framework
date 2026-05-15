"""Plugin initialization entry point for spakky-auth."""

from spakky.auth.aspects import AsyncAuthorizationAspect, AuthorizationAspect
from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-auth package.

    Registers auth AOP enforcement components. Provider implementations,
    startup validation, and boundary AuthContext seeding are added by
    downstream auth issues.
    """
    app.add(AuthorizationAspect)
    app.add(AsyncAuthorizationAspect)
