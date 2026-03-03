from spakky.domain.application.command import (
    AbstractCommand,
)


def test_abstract_command() -> None:
    """AbstractCommand의 인스턴스를 생성할 수 있음을 검증한다."""

    class TestCommand(AbstractCommand):
        pass

    command = TestCommand()
    assert isinstance(command, AbstractCommand)
