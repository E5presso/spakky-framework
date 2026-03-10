from click.testing import Result
from typer import Typer
from typer.testing import CliRunner


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
