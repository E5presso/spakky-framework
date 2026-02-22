from spakky.domain.application.command import (
    AbstractCommand,
)


def test_abstract_command() -> None:
    """Test AbstractCommand creation."""

    class TestCommand(AbstractCommand):
        pass

    command = TestCommand()
    assert isinstance(command, AbstractCommand)
