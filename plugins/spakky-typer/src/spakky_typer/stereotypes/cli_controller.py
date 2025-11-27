"""CLI controller stereotype for Typer command grouping.

Provides the @CliController stereotype for marking classes as CLI controllers
with automatic command registration and the @command decorator for methods.
"""

from dataclasses import dataclass
from typing import Any, Callable

from spakky.core.annotation import FunctionAnnotation
from spakky.core.types import AnyT, FuncT
from spakky.pod.annotations.pod import Pod
from typer.core import TyperCommand as TyperCommandClass
from typer.models import Default

from spakky_typer.utils.casing import pascal_to_kebab


@dataclass
class TyperCommand(FunctionAnnotation):
    """Function annotation for marking methods as Typer CLI commands.

    Stores all Typer command configuration including name, help text,
    and command options.

    Attributes:
        name: Command name (defaults to method name in kebab-case).
        cls: Custom Typer command class.
        context_settings: Click context settings.
        help: Command help text.
        epilog: Text displayed after command help.
        short_help: Short help text for command list.
        options_metavar: Metavar for options display.
        add_help_option: Whether to add --help option.
        no_args_is_help: Show help when no args provided.
        hidden: Hide command from help output.
        deprecated: Mark command as deprecated.
        rich_help_panel: Rich console help panel name.
    """

    name: str | None = None
    cls: type[TyperCommandClass] | None = None
    context_settings: dict[Any, Any] | None = None
    help: str | None = None
    epilog: str | None = None
    short_help: str | None = None
    options_metavar: str = "[OPTIONS]"
    add_help_option: bool = True
    no_args_is_help: bool = False
    hidden: bool = False
    deprecated: bool = False
    rich_help_panel: str | None = Default(None)


def command(
    name: str | None = None,
    cls: type[TyperCommandClass] | None = None,
    context_settings: dict[Any, Any] | None = None,
    help: str | None = None,
    epilog: str | None = None,
    short_help: str | None = None,
    options_metavar: str = "[OPTIONS]",
    add_help_option: bool = True,
    no_args_is_help: bool = False,
    hidden: bool = False,
    deprecated: bool = False,
    rich_help_panel: str | None = Default(None),
) -> Callable[[FuncT], FuncT]:
    """Decorator to mark a controller method as a CLI command.

    Attaches Typer command configuration to the method which will be registered
    by the TyperCLIPostProcessor during container initialization.

    Args:
        name: Command name (defaults to method name in kebab-case).
        cls: Custom Typer command class.
        context_settings: Click context settings.
        help: Command help text.
        epilog: Text displayed after command help.
        short_help: Short help text for command list.
        options_metavar: Metavar for options display.
        add_help_option: Whether to add --help option.
        no_args_is_help: Show help when no args provided.
        hidden: Hide command from help output.
        deprecated: Mark command as deprecated.
        rich_help_panel: Rich console help panel name.

    Returns:
        A decorator function that attaches the command configuration.
    """

    def wrapper(method: FuncT) -> FuncT:
        return TyperCommand(
            name=name,
            cls=cls,
            context_settings=context_settings,
            help=help,
            epilog=epilog,
            short_help=short_help,
            options_metavar=options_metavar,
            add_help_option=add_help_option,
            no_args_is_help=no_args_is_help,
            hidden=hidden,
            deprecated=deprecated,
            rich_help_panel=rich_help_panel,
        )(method)

    return wrapper


@dataclass(eq=False)
class CliController(Pod):
    """Stereotype for Typer CLI controllers.

    Marks a class as a CLI controller with automatic command registration.
    Methods decorated with @command will be registered as CLI commands under
    the specified group name.

    Attributes:
        group_name: CLI command group name (defaults to class name in kebab-case).
    """

    group_name: str | None = None
    """CLI command group name for organizing related commands."""

    def __call__(self, obj: AnyT) -> AnyT:
        """Apply the CLI controller stereotype to a class.

        Automatically generates the group name from the class name if not provided.

        Args:
            obj: The class to decorate.

        Returns:
            The decorated class registered as a Pod.
        """
        if self.group_name is None:
            self.group_name = pascal_to_kebab(
                obj.__name__  # pyrefly: ignore  # type: ignore
            )
        return super().__call__(obj)
