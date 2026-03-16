# CLI 애플리케이션 (Typer)

`spakky-typer`는 Typer CLI 앱을 `@CliController` 클래스로 구조화합니다.

---

## 기본 설정

```python
from typer import Typer
from spakky.core.pod.annotations.pod import Pod
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import apps

@Pod(name="cli")
def get_cli() -> Typer:
    return Typer()

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(apps)
    .add(get_cli)
    .start()
)

cli: Typer = app.container.get(type_=Typer)
```

---

## @CliController — CLI 명령 그룹

`@CliController`는 클래스를 CLI 명령 그룹으로 등록합니다. `group_name`을 생략하면 클래스명에서 자동으로 kebab-case 이름이 생성됩니다.
메서드에는 독립 함수인 `@command()`를 사용합니다.

```python
from spakky.plugins.typer.stereotypes.cli_controller import CliController, command

@CliController("users")
class UserCLI:
    _service: UserService

    def __init__(self, service: UserService) -> None:
        self._service = service

    @command("create")
    def create_user(self, name: str, email: str) -> None:
        """새 사용자 생성"""
        user = self._service.create(name, email)
        print(f"사용자 생성됨: {user.name} ({user.email})")

    @command("list")
    def list_users(self) -> None:
        """모든 사용자 조회"""
        for user in self._service.list_all():
            print(f"- {user.name}: {user.email}")

    @command("delete")
    def delete_user(self, user_id: str) -> None:
        """사용자 삭제"""
        self._service.delete(user_id)
        print(f"삭제됨: {user_id}")
```

실행 예시:

```bash
python main.py users create --name "John" --email "john@example.com"
python main.py users list
python main.py users delete --user-id "user-123"
```

---

## 여러 컨트롤러

여러 `@CliController`를 정의하면 자동으로 하위 명령 그룹이 생성됩니다.
`group_name`을 생략하면 클래스명이 kebab-case로 변환됩니다 (예: `DatabaseCLI` → `database-cli`).

```python
@CliController("db")
class DatabaseCLI:
    @command("migrate")
    def migrate(self) -> None:
        """데이터베이스 마이그레이션 실행"""
        print("Migration running...")

    @command("seed")
    def seed(self) -> None:
        """초기 데이터 삽입"""
        print("Seeding data...")

# python main.py db migrate
# python main.py db seed
```

---

## DI 주입

일반 `@Pod`처럼 생성자 주입이 동작합니다.

```python
from spakky.core.stereotype.usecase import UseCase

@UseCase()
class ImportDataUseCase:
    def execute(self, path: str) -> int:
        # 파일에서 데이터 임포트
        return 42

@CliController("data")
class DataCLI:
    _use_case: ImportDataUseCase

    def __init__(self, use_case: ImportDataUseCase) -> None:
        self._use_case = use_case

    @command("import")
    def import_data(self, path: str) -> None:
        """데이터 파일 임포트"""
        count = self._use_case.execute(path)
        print(f"{count}건 임포트 완료")
```
