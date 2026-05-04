"""Typer command adapter for actuator status output."""

from json import dumps
from os import getenv

from spakky.actuator.result import (
    ActuatorHealthResult,
    ActuatorInfoResult,
    ComponentHealthResult,
)
from spakky.actuator.service import ActuatorAggregationService
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.core.stereotype.configuration import Configuration
from typer import Typer, echo
from typing import override

ACTUATOR_COMMAND_ENABLED_ENV = "SPAKKY_TYPER_ACTUATOR_COMMAND_ENABLED"
ACTUATOR_COMMAND_NAME_ENV = "SPAKKY_TYPER_ACTUATOR_COMMAND_NAME"


@Configuration()
class ActuatorTyperConfig:
    """Configuration for Typer actuator command exposure."""

    command_enabled: bool
    command_name: str

    def __init__(
        self,
        command_enabled: bool | None = None,
        command_name: str | None = None,
    ) -> None:
        """Initialize Typer actuator command configuration."""
        self.command_enabled = (
            _env_bool(ACTUATOR_COMMAND_ENABLED_ENV, default=True)
            if command_enabled is None
            else command_enabled
        )
        self.command_name = (
            getenv(ACTUATOR_COMMAND_NAME_ENV, "actuator")
            if command_name is None
            else command_name
        )


@Order(1)
@Pod()
class ActuatorTyperCommandPostProcessor(
    IPostProcessor,
    IContainerAware,
    IApplicationContextAware,
):
    """Register actuator commands when the actuator core service is loaded."""

    __app: Typer
    __config: ActuatorTyperConfig
    __container: IContainer
    __application_context: IApplicationContext
    __registered: bool

    def __init__(self, app: Typer, config: ActuatorTyperConfig) -> None:
        """Initialize with Typer app and actuator command configuration."""
        self.__app = app
        self.__config = config
        self.__registered = False

    @override
    def set_container(self, container: IContainer) -> None:
        """Set the DI container used by command invocations."""
        self.__container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Set the application context used to clear CLI invocation scope."""
        self.__application_context = application_context

    @override
    def post_process(self, pod: object) -> object:
        """Register actuator command group after actuator service is available."""
        if self.__registered:
            return pod
        if not self.__config.command_enabled:
            return pod
        if not isinstance(pod, ActuatorAggregationService):
            return pod
        self.__app.add_typer(self.__command_group())
        self.__registered = True
        return pod

    def __command_group(self) -> Typer:
        command_group = Typer(name=self.__config.command_name)

        @command_group.command("health")
        def health() -> None:
            self.__print_health(self.__service().evaluate_health())

        @command_group.command("readiness")
        def readiness() -> None:
            self.__print_health(self.__service().evaluate_readiness())

        @command_group.command("liveness")
        def liveness() -> None:
            self.__print_health(self.__service().evaluate_liveness())

        @command_group.command("info")
        def info() -> None:
            self.__print_info(self.__service().evaluate_info())

        return command_group

    def __service(self) -> ActuatorAggregationService:
        self.__application_context.clear_context()
        return self.__container.get(ActuatorAggregationService)

    def __print_health(self, result: ActuatorHealthResult) -> None:
        echo(dumps(_health_payload(result), sort_keys=True))

    def __print_info(self, result: ActuatorInfoResult) -> None:
        echo(dumps({"info": dict(result.info)}, sort_keys=True))


def _health_payload(result: ActuatorHealthResult) -> dict[str, object]:
    return {
        "components": [
            _component_payload(component) for component in result.components
        ],
        "endpoint": result.endpoint.value,
        "status": result.status.value,
    }


def _component_payload(result: ComponentHealthResult) -> dict[str, object]:
    return {
        "details": dict(result.details),
        "name": result.name,
        "required": result.required,
        "status": result.status.value,
    }


def _env_bool(name: str, *, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
