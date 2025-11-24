from spakky.stereotype.usecase import UseCase

from spakky_typer.stereotypes.cli_controller import CliController, command


@UseCase()
class DummyUseCase:
    async def execute(self) -> str:
        return "Just Use Case!"


@CliController()
class DummyController:
    __name: str

    def __init__(self, name: str) -> None:
        self.__name = name

    async def just_function(self) -> str:
        return "Just Function!"

    @command()
    def sync_function(self) -> None:
        print("It is synchronous!")

    @command()
    async def first_command(self) -> None:
        print("First Command!")

    @command()
    async def second_command(self) -> None:
        print("Second Command!")

    @command("name")
    async def get_name(self) -> None:
        print(f"name: {self.__name}")


@CliController("second")
class SecondDummyController:
    __usecase: DummyUseCase

    def __init__(self, usecase: DummyUseCase) -> None:
        self.__usecase = usecase

    @command("dummy")
    async def execute_dummy(self) -> None:
        print(await self.__usecase.execute())
