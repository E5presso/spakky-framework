"""Feature-local contribution contract for auth providers."""

from dataclasses import dataclass

from spakky.auth.capability import AuthCapability

AUTH_CONTRIBUTION_ENTRY_POINT_GROUP = "spakky.contributions.spakky.auth"
"""Entry point group used by providers contributing to spakky-auth."""

type AuthContributionProviderId = str


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthProviderContribution:
    """Provider contribution metadata consumed by auth startup validation."""

    provider_id: AuthContributionProviderId
    """Stable provider-neutral contribution identifier."""

    capabilities: frozenset[AuthCapability]
    """Capabilities implemented by the contribution provider."""

    def supports(self, capability: AuthCapability) -> bool:
        """Return whether this contribution declares a capability."""
        return capability in self.capabilities
