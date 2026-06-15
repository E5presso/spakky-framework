from inspect import signature
from typing import Literal, override

from click.testing import Result
from pytest import MonkeyPatch
import spakky.auth
from spakky.auth import (
    AuthCapability,
    AuthContext,
    AuthInvocation,
    AuthProviderContribution,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationReasonCode,
    CredentialCarrier,
    IAuthenticationProvider,
    IScopeChecker,
    ScopeCheckRequest,
    AuthenticationError,
    AuthVerificationProviderUnavailableError,
    protected,
    require_auth_context,
    require_scope,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from typer import Option, Typer
from typer.testing import CliRunner

import spakky.plugins.typer
from spakky.plugins.typer.post_processor import _with_auth_token_option
from spakky.plugins.typer.stereotypes.cli_controller import CliController, command


@CliController("auth-boundary")
class AuthBoundaryController:
    @command("open")
    def open_command(self) -> None:
        print("open")

    @command("context")
    def context_command(self) -> None:
        require_auth_context(_AUTH_APP_CONTEXT)
        print("context")

    @command("protected")
    @protected
    def protected_command(self) -> None:
        auth_context = require_auth_context(_AUTH_APP_CONTEXT)
        print(auth_context.subject.id)

    @command("existing-token")
    @protected
    def existing_token_command(self, auth_token: str | None = None) -> None:
        auth_context = require_auth_context(_AUTH_APP_CONTEXT)
        print(f"{auth_context.subject.id}:{auth_token}")

    @command("denied")
    @require_scope("documents:write")
    def denied_command(self) -> None:
        print("denied")


@Pod()
class AllowingAuthenticationProvider(IAuthenticationProvider):
    @override
    def authenticate(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> AuthContext:
        _AUTH_CREDENTIALS.append(credential)
        _AUTH_INVOCATIONS.append(invocation)
        return AuthContext(
            subject=AuthSubject(id="cli-user"),
            issuer="issuer:test",
            credential_carrier=credential,
        )


@Pod()
class UnavailableAuthenticationProvider(IAuthenticationProvider):
    @override
    def authenticate(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> AuthContext:
        raise AuthVerificationProviderUnavailableError()


@Pod()
class InvalidAuthenticationProvider(IAuthenticationProvider):
    @override
    def authenticate(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> AuthContext:
        raise AuthenticationError()


@Pod()
class DenyingScopeChecker(IScopeChecker):
    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        return AuthorizationDecision.deny(
            AuthorizationReasonCode.INSUFFICIENT_SCOPE,
            reason="scope denied",
        )


@Pod()
def _auth_provider_contribution() -> AuthProviderContribution:
    return AuthProviderContribution(
        provider_id="typer-test",
        capabilities=frozenset(
            {
                AuthCapability.AUTHENTICATION,
                AuthCapability.SCOPE_CHECK,
            }
        ),
    )


_AUTH_CREDENTIALS: list[CredentialCarrier] = []
_AUTH_INVOCATIONS: list[AuthInvocation] = []
_AUTH_APP_CONTEXT = ApplicationContext()


def _start_auth_cli(
    *,
    include_auth_plugin: bool,
    provider: Literal["allow", "unavailable", "invalid"] | None,
    include_scope_checker: bool = True,
) -> tuple[SpakkyApplication, Typer]:
    global _AUTH_APP_CONTEXT

    _AUTH_CREDENTIALS.clear()
    _AUTH_INVOCATIONS.clear()
    _AUTH_APP_CONTEXT = ApplicationContext()
    plugins = {spakky.plugins.typer.PLUGIN_NAME}
    if include_auth_plugin:
        plugins.add(spakky.auth.PLUGIN_NAME)

    app = (
        SpakkyApplication(_AUTH_APP_CONTEXT)
        .load_plugins(include=plugins)
        .add(AuthBoundaryController)
    )
    if provider == "allow":
        app.add(AllowingAuthenticationProvider)
    if provider == "unavailable":
        app.add(UnavailableAuthenticationProvider)
    if provider == "invalid":
        app.add(InvalidAuthenticationProvider)
    if provider is not None:
        app.add(_auth_provider_contribution)
    if include_scope_checker:
        app.add(DenyingScopeChecker)
    app.start()
    return app, app.container.get(type_=Typer)


def test_sync_function(cli: Typer, runner: CliRunner) -> None:
    """동기 함수 커맨드가 정상적으로 실행됨을 검증한다."""
    result: Result = runner.invoke(cli, ["dummy-controller", "sync-function"])
    assert result.exit_code == 0
    assert result.output == "It is synchronous!\n"


def test_first_command(cli: Typer, runner: CliRunner) -> None:
    """첫 번째 커맨드가 정상적으로 실행됨을 검증한다."""
    result: Result = runner.invoke(cli, ["dummy-controller", "first-command"])
    assert result.exit_code == 0
    assert result.output == "First Command!\n"


def test_second_command(cli: Typer, runner: CliRunner) -> None:
    """두 번째 커맨드가 정상적으로 실행됨을 검증한다."""
    result: Result = runner.invoke(cli, ["dummy-controller", "second-command"])
    assert result.exit_code == 0
    assert result.output == "Second Command!\n"


def test_get_key(cli: Typer, runner: CliRunner, name: str) -> None:
    """설정된 키 값을 가져오는 커맨드가 정상적으로 실행됨을 검증한다."""
    result: Result = runner.invoke(cli, ["dummy-controller", "name"])
    assert result.exit_code == 0
    assert result.output == f"name: {name}\n"


def test_execute_dummy(cli: Typer, runner: CliRunner) -> None:
    """UseCase를 실행하는 커맨드가 정상적으로 동작함을 검증한다."""
    result: Result = runner.invoke(cli, ["second", "dummy"])
    assert result.exit_code == 0
    assert result.output == "Just Use Case!\n"


def test_protected_command_seeds_auth_context_from_option(
    runner: CliRunner,
    monkeypatch: MonkeyPatch,
) -> None:
    """--auth-token 옵션이 env var보다 우선하여 AuthContext를 seed한다."""
    monkeypatch.setenv("SPAKKY_AUTH_TOKEN", "env-token")
    app, auth_cli = _start_auth_cli(include_auth_plugin=True, provider="allow")
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "protected", "--auth-token", "option-token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 0
    assert result.output == "cli-user\n"
    assert _AUTH_CREDENTIALS[0].material == "option-token"
    assert _AUTH_CREDENTIALS[0].location.value == "CLI_OPTION"
    assert _AUTH_INVOCATIONS[0].boundary == "CLI"


def test_protected_command_uses_env_token(
    runner: CliRunner, monkeypatch: MonkeyPatch
) -> None:
    """SPAKKY_AUTH_TOKEN env var를 옵션 부재 시 전달체로 사용한다."""
    monkeypatch.setenv("SPAKKY_AUTH_TOKEN", "env-token")
    app, auth_cli = _start_auth_cli(include_auth_plugin=True, provider="allow")
    try:
        result = runner.invoke(auth_cli, ["auth-boundary", "protected"])
    finally:
        app.stop()

    assert result.exit_code == 0
    assert result.output == "cli-user\n"
    assert _AUTH_CREDENTIALS[0].material == "env-token"


def test_stdin_is_not_auth_carrier(runner: CliRunner) -> None:
    """stdin 입력은 auth 전달체로 취급하지 않는다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=False, provider=None)
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "protected"],
            input="stdin-token\n",
        )
    finally:
        app.stop()

    assert result.exit_code == 2
    assert result.output == "MISSING_CREDENTIAL\n"


def test_command_without_auth_decorator_is_allowed(runner: CliRunner) -> None:
    """auth decorator가 없는 CLI command는 provider 없이 허용한다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=False, provider=None)
    try:
        result = runner.invoke(auth_cli, ["auth-boundary", "open"])
    finally:
        app.stop()

    assert result.exit_code == 0
    assert result.output == "open\n"


def test_command_without_auth_decorator_ignores_global_token_without_provider(
    runner: CliRunner,
    monkeypatch: MonkeyPatch,
) -> None:
    """decorator가 없는 command는 global token이 있어도 provider 없이 허용한다."""
    monkeypatch.setenv("SPAKKY_AUTH_TOKEN", "env-token")
    app, auth_cli = _start_auth_cli(include_auth_plugin=False, provider=None)
    try:
        result = runner.invoke(auth_cli, ["auth-boundary", "open"])
    finally:
        app.stop()

    assert result.exit_code == 0
    assert result.output == "open\n"


def test_protected_command_fails_closed_without_token(runner: CliRunner) -> None:
    """보호된 CLI command는 token 부재 시 CHALLENGE로 fail-closed 된다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=False, provider=None)
    try:
        result = runner.invoke(auth_cli, ["auth-boundary", "protected"])
    finally:
        app.stop()

    assert result.exit_code == 2
    assert result.output == "MISSING_CREDENTIAL\n"


def test_denied_command_exits_with_deny_reason_code(runner: CliRunner) -> None:
    """authorization DENY는 exit code 3과 reason code 메시지를 출력한다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=True, provider="allow")
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "denied", "--auth-token", "valid-token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 3
    assert result.output == "INSUFFICIENT_SCOPE\nscope denied\n"


def test_provider_unavailable_exits_with_error_reason_code(runner: CliRunner) -> None:
    """provider 부재는 exit code 1과 ERROR reason code를 출력한다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=False, provider=None)
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "protected", "--auth-token", "token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 1
    assert result.output == "VERIFICATION_PROVIDER_UNAVAILABLE\n"


def test_auth_provider_unavailable_error_maps_to_error(runner: CliRunner) -> None:
    """provider unavailable 예외도 ERROR reason code로 매핑한다."""
    app, auth_cli = _start_auth_cli(
        include_auth_plugin=True,
        provider="unavailable",
    )
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "protected", "--auth-token", "token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 1
    assert result.output == "VERIFICATION_PROVIDER_UNAVAILABLE\n"


def test_authentication_error_maps_to_challenge(runner: CliRunner) -> None:
    """authentication failure는 CHALLENGE reason code로 매핑한다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=True, provider="invalid")
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "protected", "--auth-token", "bad-token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 2
    assert result.output == "INVALID_CREDENTIAL\n"


def test_method_auth_context_lookup_failure_maps_to_challenge(
    runner: CliRunner,
) -> None:
    """method 내부 AuthContext 조회 실패도 CHALLENGE로 fail-closed 된다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=False, provider=None)
    try:
        result = runner.invoke(auth_cli, ["auth-boundary", "context"])
    finally:
        app.stop()

    assert result.exit_code == 2
    assert result.output == "MISSING_CREDENTIAL\n"


def test_authorization_provider_unavailable_maps_to_error(runner: CliRunner) -> None:
    """authorization provider 부재는 ERROR reason code로 매핑한다."""
    app, auth_cli = _start_auth_cli(
        include_auth_plugin=True,
        provider="allow",
        include_scope_checker=False,
    )
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "denied", "--auth-token", "valid-token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 1
    assert result.output == "VERIFICATION_PROVIDER_UNAVAILABLE\n"


def test_existing_auth_token_signature_parameter_is_preserved() -> None:
    """public auth_token parameter가 이미 있으면 signature를 중복 확장하지 않는다."""

    def command_with_auth_token(*, auth_token: str | None = None) -> None:
        return None

    assert _with_auth_token_option(command_with_auth_token) == signature(
        command_with_auth_token
    )


def test_existing_auth_token_option_decl_is_preserved() -> None:
    """기존 --auth-token option 선언도 중복 확장하지 않는다."""

    def command_with_auth_option(
        token: str | None = Option(None, "--auth-token"),
    ) -> None:
        return None

    assert _with_auth_token_option(command_with_auth_option) == signature(
        command_with_auth_option
    )


def test_non_auth_token_option_still_gets_internal_auth_option() -> None:
    """다른 option 선언은 내부 auth option 추가를 막지 않는다."""

    def command_with_other_option(
        token: str | None = Option(None, "--token"),
    ) -> None:
        return None

    assert (
        "_spakky_auth_token"
        in _with_auth_token_option(command_with_other_option).parameters
    )


def test_existing_auth_token_option_is_preserved_and_used_for_seeding(
    runner: CliRunner,
) -> None:
    """기존 --auth-token 옵션은 command 인자와 auth seed에 모두 보존된다."""
    app, auth_cli = _start_auth_cli(include_auth_plugin=True, provider="allow")
    try:
        result = runner.invoke(
            auth_cli,
            ["auth-boundary", "existing-token", "--auth-token", "existing-token"],
        )
    finally:
        app.stop()

    assert result.exit_code == 0
    assert result.output == "cli-user:existing-token\n"
    assert _AUTH_CREDENTIALS[0].material == "existing-token"
