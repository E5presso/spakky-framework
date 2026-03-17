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
    <img src="https://github.com/E5presso/spakky-framework/actions/workflows/ci.yml/badge.svg" alt="CI Status">
  </a>
  <a href="https://codecov.io/gh/E5presso/spakky-framework">
    <img src="https://codecov.io/gh/E5presso/spakky-framework/branch/develop/graph/badge.svg" alt="Codecov">
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

### Core Packages

| Package | Description |
|---------|--------------|
| **`spakky`** | Core framework (DI Container, AOP, Application Context) |
| **`spakky-domain`** | DDD building blocks (Entity, AggregateRoot, ValueObject, DomainEvent, CQRS) |
| **`spakky-data`** | Data access abstractions (Repository, Transaction, External Proxy) |
| **`spakky-event`** | Event handling (IEventPublisher, IEventBus, IEventTransport, @EventHandler) |
| **`spakky-task`** | Task queue abstractions (@TaskHandler, @task, @schedule, Crontab) |
| **`spakky-outbox`** | Transactional Outbox pattern for reliable event delivery |

### Plugins

| Package | Description |
|---------|--------------|
| **`spakky-fastapi`** | Integration with [FastAPI](https://fastapi.tiangolo.com/) for building REST APIs |
| **`spakky-kafka`** | Event-driven architecture support with [Apache Kafka](https://kafka.apache.org/) |
| **`spakky-rabbitmq`** | Event-driven architecture support with [RabbitMQ](https://www.rabbitmq.com/) |
| **`spakky-security`** | Security utilities (Cryptography, Password Hashing, JWT) |
| **`spakky-sqlalchemy`** | Database integration with [SQLAlchemy](https://www.sqlalchemy.org/) ORM |
| **`spakky-typer`** | CLI application support with [Typer](https://typer.tiangolo.com/) |
| **`spakky-celery`** | Task dispatch and schedule registration with [Celery](https://docs.celeryq.dev/) via AOP |

## 🚀 Quick Start

### Documentation

The official documentation is available at [framework.spakky.com](https://framework.spakky.com).

### Installation

Install the core framework:

```bash
pip install spakky
```

Or install with plugins:

```bash
pip install "spakky[fastapi,kafka]"
```
