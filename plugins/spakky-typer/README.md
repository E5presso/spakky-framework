# Spakky Typer

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 Typer CLI 통합 플러그인입니다.

## 설치

```bash
pip install spakky-typer
```

Spakky extras로도 설치할 수 있습니다.

```bash
pip install spakky[typer]
```

## 주요 기능

- **자동 command 등록**: `@CliController` 클래스에서 command를 등록합니다.
- **비동기 지원**: CLI command에서 async/await 전체 지원
- **Command grouping**: command를 논리적 group으로 구성
- **의존성 주입**: 서비스가 controller에 자동 주입
- **Rich 통합**: Typer의 rich console output 활용
- **Actuator command**: `spakky-actuator` 로드 시 `actuator` 상태 command 등록

## 사용법

### 기본 CLI Controller

```python
from spakky.plugins.typer.stereotypes.cli_controller import CliController, command

@CliController("user")
class UserCliController:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    @command("list")
    async def list_users(self) -> None:
        """모든 user를 나열합니다."""
        users = await self.user_service.list_all()
        for user in users:
            print(f"{user.id}: {user.name}")

    @command("create")
    async def create_user(self, name: str, email: str) -> None:
        """새 user를 생성합니다."""
        user = await self.user_service.create(name, email)
        print(f"Created user: {user.id}")

    @command("delete")
    async def delete_user(self, user_id: int) -> None:
        """ID로 user를 삭제합니다."""
        await self.user_service.delete(user_id)
        print(f"Deleted user: {user_id}")
```

### CLI 사용

```bash
# 모든 user 나열
python main.py user list

# 새 user 생성
python main.py user create --name "John Doe" --email "john@example.com"

# user 삭제
python main.py user delete --user-id 123
```

### Command 옵션

```python
from spakky.plugins.typer.stereotypes.cli_controller import CliController, command

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
        """pending database migration을 실행합니다."""
        if dry_run:
            print("Dry run mode - no changes will be made")
        # migration logic

    @command("seed", hidden=True)  # help output에서 숨김
    async def seed_database(self) -> None:
        """test data로 database를 seed합니다."""
        pass

    @command("status", deprecated=True)  # deprecated 표시
    async def check_status(self) -> None:
        """database connection status를 확인합니다."""
        pass
```

### Typer 인스턴스 접근

```python
from typer import Typer
from spakky.core.application.application import SpakkyApplication

# application.start() 이후
typer_app = application.container.get(Typer)

# CLI 실행
if __name__ == "__main__":
    typer_app()
```

### Actuator command

`spakky-typer`와 `spakky-actuator`를 함께 로드하면 플러그인이 `actuator` command group을 등록합니다:

```bash
python main.py actuator health
python main.py actuator readiness
python main.py actuator liveness
python main.py actuator info
```

각 command는 transport 중립 actuator core result model에서 결정적 JSON을 출력합니다.
`readiness`는 앱이 작업을 받을 준비가 되었는지 보고합니다. `liveness`는 프로세스 내부 check로 남아야 하며 외부 의존성을 사용할 수 없다는 이유만으로 실패하면 안 됩니다.

command 등록은 다음으로 비활성화합니다:

```bash
export SPAKKY_TYPER_ACTUATOR_COMMAND_ENABLED=false
```

command group 이름은 다음으로 변경합니다:

```bash
export SPAKKY_TYPER_ACTUATOR_COMMAND_NAME=status
```

Typer adapter는 플러그인별 상세 check를 자동 등록하지 않습니다.
데이터베이스, broker, worker readiness가 command 출력에 영향을 줘야 한다면 애플리케이션에 `spakky.actuator.AbstractHealthProbe` Pod를 등록하세요.

### 애플리케이션 설정

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
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

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `CliController` | CLI command group용 stereotype |
| `command` | CLI command용 decorator |
| `TyperCLIPostProcessor` | 자동 command 등록 post-processor |

## Command decorator 옵션

| 옵션 | 타입 | 설명 |
|--------|------|-------------|
| `name` | `str` | command 이름(기본값은 kebab-case 메서드명) |
| `help` | `str` | command 전체 help text |
| `short_help` | `str` | command 목록용 짧은 help text |
| `epilog` | `str` | command help 뒤에 표시할 text |
| `hidden` | `bool` | help output에서 command 숨김 |
| `deprecated` | `bool` | command를 deprecated로 표시 |
| `no_args_is_help` | `bool` | 인자가 없을 때 help 표시 |
| `add_help_option` | `bool` | --help option 추가 여부 |
| `rich_help_panel` | `str` | Rich console help panel 이름 |

## 라이선스

MIT
