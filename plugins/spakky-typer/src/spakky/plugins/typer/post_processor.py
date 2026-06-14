"""Post-processor for registering Typer CLI commands.

Automatically discovers and registers CLI commands from @CliController
decorated classes, with support for both sync and async command handlers.
"""

from functools import wraps
from inspect import Parameter, Signature, getmembers, iscoroutinefunction, signature
from logging import getLogger
import os
from typing import Any, Never, cast
from collections.abc import Callable

from spakky.auth import (
    AuthContextNotFoundError,
    AuthInvocation,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
    AuthVerificationProviderUnavailableError,
    AuthenticationError,
    AuthorizationDecision,
    AuthorizationReasonCode,
    AuthorizationDecisionState,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
    IAuthenticationProvider,
    get_effective_auth_metadata,
    store_auth_context,
)
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from typing import override

from spakky.plugins.typer.stereotypes.cli_controller import CliController, TyperCommand
from spakky.plugins.typer.utils.asyncio import run_async
from typer import Exit, Option, Typer, echo
from typer.models import OptionInfo

logger = getLogger(__name__)

AUTH_TOKEN_OPTION_PARAMETER = "_spakky_auth_token"
AUTH_TOKEN_ENV_VAR = "SPAKKY_AUTH_TOKEN"


def _auth_token_parameter() -> Parameter:
    return Parameter(
        AUTH_TOKEN_OPTION_PARAMETER,
        kind=Parameter.KEYWORD_ONLY,
        default=Option(
            None,
            "--auth-token",
            envvar=AUTH_TOKEN_ENV_VAR,
            help="Authentication bearer token.",
        ),
        annotation=str | None,
    )


def _existing_auth_token_parameter(original: Signature) -> str | None:
    for parameter in original.parameters.values():
        if parameter.name in {AUTH_TOKEN_OPTION_PARAMETER, "auth_token"}:
            return parameter.name
        if (
            isinstance(parameter.default, OptionInfo)
            and parameter.default.param_decls is not None
            and "--auth-token" in parameter.default.param_decls
        ):
            return parameter.name
    return None


def _with_auth_token_option(method: Callable[..., object]) -> Signature:
    original = signature(method)
    if _existing_auth_token_parameter(original) is not None:
        return original
    return original.replace(
        parameters=tuple(original.parameters.values()) + (_auth_token_parameter(),)
    )


def _invocation(controller_type: type[object], method_name: str) -> AuthInvocation:
    return AuthInvocation(
        boundary="CLI",
        operation=f"{controller_type.__module__}.{controller_type.__qualname__}.{method_name}",
    )


def _carrier(auth_token: str) -> CredentialCarrier:
    return CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.CLI_OPTION,
        material=auth_token,
        name="--auth-token",
        scheme="Bearer",
    )


def _exit(decision: AuthorizationDecision) -> Never:
    echo(decision.reason_code.value)
    if decision.reason is not None:
        echo(decision.reason)
    if decision.state is AuthorizationDecisionState.CHALLENGE:
        raise Exit(code=2)
    if decision.state is AuthorizationDecisionState.DENY:
        raise Exit(code=3)
    raise Exit(code=1)


@Order(0)
@Pod()
class TyperCLIPostProcessor(IPostProcessor, IContainerAware, IApplicationContextAware):
    """Post-processor that registers CLI commands from CLI controllers.

    Scans @CliController decorated classes for @command decorated methods
    and automatically registers them as Typer commands with proper dependency
    injection and async support.
    """

    __app: Typer
    __container: IContainer
    __application_context: IApplicationContext

    def __init__(self, app: Typer) -> None:
        """Initialize the Typer CLI post-processor.

        Args:
            app: The Typer application instance.
        """
        super().__init__()
        self.__app = app

    @override
    def set_container(self, container: IContainer) -> None:
        """Set the container for dependency injection.

        Args:
            container: The IoC container.
        """
        self.__container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Set the application context.

        Args:
            application_context: The application context instance.
        """
        self.__application_context = application_context

    @override
    def post_process(self, pod: object) -> object:
        """Register commands from CLI controllers.

        Scans the controller for methods decorated with @command and registers
        them as Typer commands. Automatically wraps async methods with run_async.

        Args:
            pod: The Pod to process, potentially a CLI controller.

        Returns:
            The Pod, with commands registered if it's a CLI controller.
        """
        if not CliController.exists(pod):
            return pod
        controller = CliController.get(pod)
        command_group: Typer = Typer(name=controller.group_name)
        for name, method in getmembers(pod, callable):
            command: TyperCommand | None = TyperCommand.get_or_none(method)
            if command is not None:
                auth_metadata = get_effective_auth_metadata(
                    method,
                    owner_type=controller.type_,
                )
                existing_auth_token_parameter = _existing_auth_token_parameter(
                    signature(method)
                )
                # pylint: disable=line-too-long
                logger.info(
                    f"[{type(self).__name__}] {command.name!r} -> {'async' if iscoroutinefunction(method) else ''} {method.__qualname__}"
                )

                @wraps(method)
                def endpoint(
                    *args: Any,
                    method_name: str = name,
                    controller_type: type[object] = controller.type_,
                    container: IContainer = self.__container,
                    protected: bool = auth_metadata.protected,
                    auth_token_parameter: str | None = existing_auth_token_parameter,
                    **kwargs: Any,
                ) -> Any:
                    auth_token = (
                        kwargs.get(auth_token_parameter)
                        if auth_token_parameter is not None
                        else kwargs.pop(AUTH_TOKEN_OPTION_PARAMETER, None)
                    )
                    if auth_token is None:
                        auth_token = os.environ.get(AUTH_TOKEN_ENV_VAR)
                    # CLI invocations often share the same interpreter session,
                    # so purge any context-scoped Pods to avoid cross-command leaks.
                    self.__application_context.clear_context()
                    invocation = _invocation(controller_type, method_name)
                    if isinstance(auth_token, str) and auth_token:
                        provider = container.get_or_none(IAuthenticationProvider)
                        if provider is None:
                            if protected:
                                _exit(
                                    AuthorizationDecision.error(
                                        AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
                                    )
                                )
                        else:
                            try:
                                auth_context = provider.authenticate(
                                    _carrier(auth_token),
                                    invocation,
                                )
                            except AuthVerificationProviderUnavailableError:
                                _exit(
                                    AuthorizationDecision.error(
                                        AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
                                    )
                                )
                            except AuthenticationError:
                                _exit(
                                    AuthorizationDecision.challenge(
                                        AuthorizationReasonCode.INVALID_CREDENTIAL
                                    )
                                )
                            store_auth_context(self.__application_context, auth_context)
                    elif protected:
                        _exit(
                            AuthorizationDecision.challenge(
                                AuthorizationReasonCode.MISSING_CREDENTIAL
                            )
                        )
                    controller_instance = container.get(controller_type)
                    # 프레임워크 내부: CLI 커맨드 메서드 동적 디스패치
                    method_to_call = getattr(  # command decorator method lookup
                        controller_instance, method_name
                    )
                    if iscoroutinefunction(method_to_call):
                        method_to_call = run_async(method_to_call)
                    try:
                        return method_to_call(*args, **kwargs)
                    except AuthContextNotFoundError:
                        _exit(
                            AuthorizationDecision.challenge(
                                AuthorizationReasonCode.MISSING_CREDENTIAL
                            )
                        )
                    except AuthRequirementProviderUnavailableError:
                        _exit(
                            AuthorizationDecision.error(
                                AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
                            )
                        )
                    except AuthRequirementDeniedError as error:
                        _exit(
                            error.decision
                            if error.decision is not None
                            else AuthorizationDecision.deny(
                                AuthorizationReasonCode.POLICY_DENIED
                            )
                        )

                cast(Any, endpoint).__signature__ = _with_auth_token_option(method)

                command_group.command(
                    name=command.name,
                    cls=command.cls,
                    context_settings=command.context_settings,
                    help=command.help,
                    epilog=command.epilog,
                    short_help=command.short_help,
                    options_metavar=command.options_metavar,
                    add_help_option=command.add_help_option,
                    no_args_is_help=command.no_args_is_help,
                    hidden=command.hidden,
                    deprecated=command.deprecated,
                    rich_help_panel=command.rich_help_panel,
                )(endpoint)
        self.__app.add_typer(command_group)
        return pod
