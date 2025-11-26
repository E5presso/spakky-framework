<p align="center">
  <img src="./assets/symbol.svg" width="80rem" alt="Spakky Logo">
</p>
<h1 align="center">Spakky Framework</h1>
<p align="center"><i>Build scalable Python apps with the power of DI & AOP</i></p>

<p align="center">
  <a href="https://pypi.org/project/spakky/">
    <img src="https://img.shields.io/pypi/v/spakky.svg" alt="PyPI Version">
  </a>
  <a href="#">
    <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python Versions">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License">
  </a>
</p>

<h3 align="center">⚡️ Powered by</h3>
<p align="center">
  <a href="https://github.com/astral-sh/uv">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv">
  </a>
  <a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff">
  </a>
  <a href="https://github.com/facebook/pyrefly">
    <img src="https://img.shields.io/endpoint?url=https://pyrefly.org/badge.json" alt="Pyrefly">
  </a>
</p>

<h3 align="center">✅ CI Status</h3>
<p align="center">
  <a href="https://github.com/E5presso/spakky-framework/actions/workflows/ci.yml">
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci.yml/badge.svg" alt="Core CI">
  </a>
  <a href="https://github.com/E5presso/spakky-framework/actions/workflows/ci-fastapi.yml">
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci-fastapi.yml/badge.svg" alt="FastAPI Plugin CI">
  </a>
  <a href="https://github.com/E5presso/spakky-framework/actions/workflows/ci-rabbitmq.yml">
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci-rabbitmq.yml/badge.svg" alt="RabbitMQ Plugin CI">
  </a>
  <a href="https://github.com/E5presso/spakky-framework/actions/workflows/ci-security.yml">
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci-security.yml/badge.svg" alt="Security Plugin CI">
  </a>
  <a href="https://github.com/E5presso/spakky-framework/actions/workflows/ci-typer.yml">
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci-typer.yml/badge.svg" alt="Typer Plugin CI">
  </a>
</p>

---

**Spakky** is a modern, Spring-inspired dependency injection framework for Python, designed for building scalable, modular applications with ease. It brings the power of Inversion of Control (IoC) and Aspect-Oriented Programming (AOP) to the Python ecosystem, with first-class support for **FastAPI**, **RabbitMQ**, and **Typer**.

## ✨ Features

- **Dependency Injection (DI)**: Powerful IoC container with `@Pod` decorators, supporting Singleton, Prototype, and Context scopes.
- **Aspect-Oriented Programming (AOP)**: Built-in support for `@Aspect`, `@Before`, `@After`, `@Around` to handle cross-cutting concerns like logging and transactions.
- **Modular Plugin System**: Easily extensible architecture with plugins for popular libraries.
- **Type-Safe**: Built with modern Python type hints in mind.
- **Async First**: Native support for `asyncio` and asynchronous dependency injection.

## 📦 Ecosystem

Spakky is a monorepo containing the core framework and official plugins:

| Package | Description |
|---------|-------------|
| **`spakky`** | Core framework (DI Container, AOP, Application Context) |
| **`spakky-fastapi`** | Integration with [FastAPI](https://fastapi.tiangolo.com/) for building REST APIs |
| **`spakky-rabbitmq`** | Event-driven architecture support with [RabbitMQ](https://www.rabbitmq.com/) |
| **`spakky-security`** | Security utilities (Cryptography, Password Hashing, JWT) |
| **`spakky-typer`** | CLI application support with [Typer](https://typer.tiangolo.com/) |

## 🚀 Quick Start

### Installation

Install the core framework:

```bash
pip install spakky
```

Or install with plugins:

```bash
pip install "spakky[fastapi,rabbitmq]"
```

### Basic Usage

Define your services with `@Pod`:

```python
from spakky.pod.annotations.pod import Pod

@Pod()
class UserRepository:
    def get_user(self, id: int) -> str:
        return "John Doe"

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_user_name(self, id: int) -> str:
        return self.repository.get_user(id)
```

Bootstrap the application:

```python
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .scan("my_package")
    .start()
)

user_service = app.container.get(UserService)
print(user_service.get_user_name(1))
```

## 🛠 Development

This project uses `uv` for dependency management and workspace handling.

### Prerequisites

- Python 3.11+
- `uv` installed

### Setup

```bash
# Clone the repository
git clone https://github.com/E5presso/spakky-framework.git
cd spakky-framework

# Sync dependencies (from workspace root)
uv sync --all-packages --all-extras
```

> **💡 Note:** Use `--all-packages` only at the workspace root. When working inside a sub-package (e.g., `cd plugins/spakky-fastapi`), use `uv sync --all-extras` instead.

### Running Tests

```bash
# Run all tests
uv run pytest

# Run tests for a specific package
uv run pytest plugins/spakky-fastapi
```

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the MIT License.
