# Spakky Typer

Typer CLI integration plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-typer
```

Or install via Spakky extras:

```bash
pip install spakky[typer]
```

## Features

- **Automatic command registration**: Commands are registered from `@CliController` classes
- **Async support**: Full async/await support for CLI commands
- **Command grouping**: Organize commands into logical groups
- **Dependency injection**: Services are automatically injected into controllers
- **Rich integration**: Leverages Typer's rich console output

## Usage

### Basic CLI Controller

```python
from spakky_typer.stereotypes.cli_controller import CliController, command

@CliController("user")
class UserCliController:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    @command("list")
    async def list_users(self) -> None:
        """List all users."""
        users = await self.user_service.list_all()
        for user in users:
            print(f"{user.id}: {user.name}")

    @command("create")
    async def create_user(self, name: str, email: str) -> None:
        """Create a new user."""
        user = await self.user_service.create(name, email)
        print(f"Created user: {user.id}")

    @command("delete")
    async def delete_user(self, user_id: int) -> None:
        """Delete a user by ID."""
        await self.user_service.delete(user_id)
        print(f"Deleted user: {user_id}")
```

### CLI Usage

```bash
# List all users
python main.py user list

# Create a new user
python main.py user create --name "John Doe" --email "john@example.com"

# Delete a user
python main.py user delete --user-id 123
```

### Command Options

```python
from spakky_typer.stereotypes.cli_controller import CliController, command

@CliController("db")
class DatabaseCliController:
    @command(
        name="migrate",
        help="Run database migrations",
        short_help="Run migrations",
        epilog="Use --dry-run to preview changes",
    )
    async def run_migrations(
        self,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        """Execute pending database migrations."""
        if dry_run:
            print("Dry run mode - no changes will be made")
        # Migration logic here

    @command("seed", hidden=True)  # Hidden from help output
    async def seed_database(self) -> None:
        """Seed database with test data."""
        pass

    @command("status", deprecated=True)  # Mark as deprecated
    async def check_status(self) -> None:
        """Check database connection status."""
        pass
```

### Accessing Typer Instance

```python
from typer import Typer
from spakky.application.application import SpakkyApplication

# After application.start()
typer_app = application.container.get(Typer)

# Run the CLI
if __name__ == "__main__":
    typer_app()
```

### Application Setup

```python
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from typer import Typer
import my_cli_module

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(my_cli_module)
    .start()
)

typer_app = app.container.get(Typer)

if __name__ == "__main__":
    typer_app()
```

## Components

| Component | Description |
|-----------|-------------|
| `CliController` | Stereotype for CLI command groups |
| `command` | Decorator for CLI commands |
| `TyperCLIPostProcessor` | Automatic command registration post-processor |

## Command Decorator Options

| Option | Type | Description |
|--------|------|-------------|
| `name` | `str` | Command name (defaults to method name in kebab-case) |
| `help` | `str` | Full help text for the command |
| `short_help` | `str` | Short help text for command list |
| `epilog` | `str` | Text displayed after command help |
| `hidden` | `bool` | Hide command from help output |
| `deprecated` | `bool` | Mark command as deprecated |
| `no_args_is_help` | `bool` | Show help when no args provided |
| `add_help_option` | `bool` | Whether to add --help option |
| `rich_help_panel` | `str` | Rich console help panel name |

## License

MIT
