"""Built-in resolver for invocation-scoped auth references."""

from typing import override

from spakky.auth.error import AuthDynamicRefUnresolvedError
from spakky.auth.invocation import (
    AuthDynamicRef,
    AuthInvocation,
    ResolvedAuthReference,
)
from spakky.auth.ports import IAuthInvocationResolver


class AuthInvocationAttributeResolver(IAuthInvocationResolver):
    """Resolve a dynamic ref by reading the invocation attribute it names.

    The expression is the attribute name, for example
    `http.header.x-workspace`. Authorization uses this resolver when the
    application registers no IAuthInvocationResolver of its own.
    """

    @override
    def resolve_ref(
        self,
        invocation: AuthInvocation,
        dynamic_ref: AuthDynamicRef,
    ) -> ResolvedAuthReference:
        """Return the named attribute as the reference value.

        Raises:
            AuthDynamicRefUnresolvedError: The attribute is absent, empty, or
                not a string.
        """
        for attribute in invocation.attributes:
            if attribute.name != dynamic_ref.expression:
                continue
            if isinstance(attribute.value, str) and attribute.value != "":
                return ResolvedAuthReference(
                    kind=dynamic_ref.kind,
                    value=attribute.value,
                )
        raise AuthDynamicRefUnresolvedError(dynamic_ref.expression)
