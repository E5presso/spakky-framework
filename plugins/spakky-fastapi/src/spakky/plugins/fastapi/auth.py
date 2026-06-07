"""Authentication boundary helpers for FastAPI routes."""

from inspect import Parameter, Signature, signature

from fastapi import Request, WebSocket

from spakky.auth import (
    AbstractSpakkyAuthError,
    AuthContextNotFoundError,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
    AuthenticationError,
    ConflictingAuthMetadataError,
    CredentialCarrier,
    CredentialCarrierError,
    CredentialCarrierKind,
    CredentialCarrierLocation,
    IAuthenticationProvider,
    get_effective_auth_metadata,
    store_auth_context,
)
from spakky.core.common.types import Func
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.fastapi.error import Forbidden, InternalServerError, Unauthorized

HTTP_AUTH_REQUEST_PARAMETER = "__spakky_auth_request"
WEBSOCKET_AUTH_PARAMETER = "__spakky_auth_websocket"

AUTHORIZATION_HEADER_NAME = "authorization"
BEARER_SCHEME = "Bearer"
BEARER_PREFIX = f"{BEARER_SCHEME} "
WEBSOCKET_QUERY_TOKEN_NAME = "access_token"

HTTP_BOUNDARY = "HTTP"
WEBSOCKET_BOUNDARY = "WEBSOCKET"
WEBSOCKET_AUTH_CHALLENGE_CLOSE_CODE = 1008
WEBSOCKET_AUTH_ERROR_CLOSE_CODE = 1011


class FastAPIAuthBoundary:
    """Seed AuthContext and map auth failures at FastAPI boundaries."""

    _container: IContainer
    _application_context: IApplicationContext

    def __init__(
        self,
        container: IContainer,
        application_context: IApplicationContext,
    ) -> None:
        self._container = container
        self._application_context = application_context

    def seed_http_auth_context(self, request: Request, boundary: Func) -> None:
        """Authenticate an HTTP credential and seed AuthContext when present."""
        metadata = get_effective_auth_metadata(boundary)
        credential = self._http_credential(request)
        if credential is None:
            if metadata.protected:
                raise AuthContextNotFoundError()
            return
        provider = self._container.get_or_none(IAuthenticationProvider)
        if provider is None:
            if metadata.protected:
                raise AuthRequirementProviderUnavailableError()
            return
        try:
            auth_context = provider.authenticate(
                credential,
                self._http_invocation(request, boundary),
            )
        except (AuthenticationError, CredentialCarrierError):
            if metadata.protected:
                raise
            return
        store_auth_context(self._application_context, auth_context)

    def seed_websocket_auth_context(
        self,
        websocket: WebSocket,
        boundary: Func,
    ) -> None:
        """Authenticate a WebSocket credential and seed AuthContext when present."""
        metadata = get_effective_auth_metadata(boundary)
        credential = self._websocket_credential(websocket)
        if credential is None:
            if metadata.protected:
                raise AuthContextNotFoundError()
            return
        provider = self._container.get_or_none(IAuthenticationProvider)
        if provider is None:
            if metadata.protected:
                raise AuthRequirementProviderUnavailableError()
            return
        try:
            auth_context = provider.authenticate(
                credential,
                self._websocket_invocation(websocket, boundary),
            )
        except (AuthenticationError, CredentialCarrierError):
            if metadata.protected:
                raise
            return
        store_auth_context(self._application_context, auth_context)

    def map_http_auth_error(self, error: AbstractSpakkyAuthError) -> None:
        """Raise the FastAPI HTTP error corresponding to an auth failure."""
        if isinstance(
            error,
            (AuthContextNotFoundError, AuthenticationError, CredentialCarrierError),
        ):
            raise Unauthorized() from error
        if isinstance(error, AuthRequirementDeniedError):
            raise Forbidden() from error
        if isinstance(
            error,
            (AuthRequirementProviderUnavailableError, ConflictingAuthMetadataError),
        ):
            raise InternalServerError() from error
        raise InternalServerError() from error

    async def close_websocket_for_auth_error(
        self,
        websocket: WebSocket,
        error: AbstractSpakkyAuthError,
    ) -> None:
        """Close a WebSocket with the code matching the auth failure class."""
        code = WEBSOCKET_AUTH_ERROR_CLOSE_CODE
        if isinstance(
            error,
            (AuthContextNotFoundError, AuthenticationError, AuthRequirementDeniedError),
        ):
            code = WEBSOCKET_AUTH_CHALLENGE_CLOSE_CODE
        await websocket.close(code=code)

    def signature_with_request(self, boundary: Func) -> Signature:
        """Return a FastAPI signature that injects Request without user handlers."""
        return self._signature_with_boundary_parameter(
            boundary,
            HTTP_AUTH_REQUEST_PARAMETER,
            Request,
        )

    def signature_with_websocket(self, boundary: Func) -> Signature:
        """Return a FastAPI signature that injects WebSocket without auth-only args."""
        return self._signature_with_boundary_parameter(
            boundary,
            WEBSOCKET_AUTH_PARAMETER,
            WebSocket,
        )

    def request_argument_names(self, boundary: Func) -> tuple[str, ...]:
        """Return user handler parameter names that expect FastAPI Request."""
        return self._argument_names_with_annotation(boundary, Request)

    def websocket_argument_names(self, boundary: Func) -> tuple[str, ...]:
        """Return user handler parameter names that expect FastAPI WebSocket."""
        return self._argument_names_with_annotation(boundary, WebSocket)

    def _http_credential(self, request: Request) -> CredentialCarrier | None:
        return self._authorization_header_credential(
            request.headers.get(AUTHORIZATION_HEADER_NAME)
        )

    def _websocket_credential(self, websocket: WebSocket) -> CredentialCarrier | None:
        header_credential = self._authorization_header_credential(
            websocket.headers.get(AUTHORIZATION_HEADER_NAME)
        )
        if header_credential is not None:
            return header_credential
        token = websocket.query_params.get(WEBSOCKET_QUERY_TOKEN_NAME)
        if token is None or token == "":
            return None
        return CredentialCarrier(
            kind=CredentialCarrierKind.BEARER_TOKEN,
            location=CredentialCarrierLocation.QUERY_PARAMETER,
            material=token,
            name=WEBSOCKET_QUERY_TOKEN_NAME,
            scheme=BEARER_SCHEME,
        )

    def _authorization_header_credential(
        self,
        value: str | None,
    ) -> CredentialCarrier | None:
        if value is None or not value.startswith(BEARER_PREFIX):
            return None
        material = value[len(BEARER_PREFIX) :]
        if material == "":
            return None
        return CredentialCarrier(
            kind=CredentialCarrierKind.BEARER_TOKEN,
            location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
            material=material,
            name=AUTHORIZATION_HEADER_NAME,
            scheme=BEARER_SCHEME,
        )

    def _http_invocation(self, request: Request, boundary: Func) -> AuthInvocation:
        return AuthInvocation(
            boundary=HTTP_BOUNDARY,
            operation=f"{request.method} {request.url.path}",
            attributes=self._invocation_attributes(boundary),
        )

    def _websocket_invocation(
        self,
        websocket: WebSocket,
        boundary: Func,
    ) -> AuthInvocation:
        return AuthInvocation(
            boundary=WEBSOCKET_BOUNDARY,
            operation=websocket.url.path,
            attributes=self._invocation_attributes(boundary),
        )

    def _invocation_attributes(
        self,
        boundary: Func,
    ) -> tuple[AuthInvocationAttribute, ...]:
        return (AuthInvocationAttribute(name="handler", value=boundary.__qualname__),)

    def _signature_with_boundary_parameter(
        self,
        boundary: Func,
        name: str,
        annotation: type[object],
    ) -> Signature:
        original = signature(boundary)
        parameter = Parameter(
            name,
            kind=Parameter.KEYWORD_ONLY,
            annotation=annotation,
        )
        parameters = list(original.parameters.values())
        for index, existing in enumerate(parameters):
            if existing.kind is Parameter.VAR_KEYWORD:
                parameters.insert(index, parameter)
                return original.replace(parameters=parameters)
        parameters.append(parameter)
        return original.replace(parameters=parameters)

    def _argument_names_with_annotation(
        self,
        boundary: Func,
        annotation: type[object],
    ) -> tuple[str, ...]:
        return tuple(
            parameter.name
            for parameter in signature(boundary).parameters.values()
            if parameter.annotation is annotation
        )
