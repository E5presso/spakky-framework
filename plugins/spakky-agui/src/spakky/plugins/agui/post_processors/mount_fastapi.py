"""Post-processor that mounts AG-UI routes on FastAPI Pods."""

from collections.abc import Callable
from logging import getLogger
from typing import override, cast

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from fastapi import FastAPI

from spakky.agent import Agent, IAgentRunnerFactory, RunAgentInput
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import RunDriverFactory, add_agui_endpoint
from spakky.plugins.agui.endpoint_input import AgUiInboundRun
from spakky.plugins.agui.error import AgUiEndpointConflictError
from spakky.plugins.agui.http_stream import add_agui_http_stream_endpoint
from spakky.plugins.agui.server.registry import AgUiAgentEntry, AgUiAgentRegistry
from spakky.plugins.agui.stereotypes.agui_agent import AgUiAgent
from spakky.plugins.agui.transport import AgUiManagedRunDriver
from spakky.plugins.agui.websocket import add_agui_websocket_endpoint

logger = getLogger(__name__)

type _EndpointRegistrar = Callable[..., None]


@Order(0)
@Pod()
class MountAgUiFastAPIPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Discover @AgUiAgent @Agent Pods and mount their AG-UI FastAPI routes."""

    _container: IContainer
    _application_context: IApplicationContext
    _claimed_paths: dict[tuple[int, str, str], str]
    _mounted: set[tuple[int, str, str]]

    def __init__(self) -> None:
        self._claimed_paths = {}
        self._mounted = set()

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self._application_context = application_context

    @staticmethod
    def _unwrap_proxy_type(pod_type: type[object]) -> type[object]:
        """Return the original class when *pod_type* is an AOP dynamic proxy."""
        if pod_type.__name__.endswith(DYNAMIC_PROXY_CLASS_NAME_SUFFIX):
            return pod_type.__bases__[0]
        return pod_type

    @override
    def post_process(self, pod: object) -> object:
        """Register exposed agents and mount them on FastAPI apps."""
        if isinstance(pod, FastAPI):
            self._mount_registered_agents(pod)
            return pod
        agent_type = self._unwrap_proxy_type(type(pod))
        if not (AgUiAgent.exists(agent_type) and Agent.exists(agent_type)):
            return pod
        registry = self._container.get(AgUiAgentRegistry)
        entry = registry.register(pod, agent_type, AgUiAgent.get(agent_type))
        for app in self._fastapi_apps():
            self._mount_entry(app, entry)
        logger.info("Registered AG-UI agent from %s", agent_type.__qualname__)
        return pod

    def _fastapi_apps(self) -> tuple[FastAPI, ...]:
        """Return all FastAPI application Pods currently registered."""
        return tuple(
            cast(FastAPI, fast_api)
            for fast_api in self._application_context.find(
                lambda pod: pod.type_ is FastAPI or FastAPI in pod.base_types
            )
        )

    def _mount_registered_agents(self, app: FastAPI) -> None:
        registry = self._container.get(AgUiAgentRegistry)
        for entry in registry.list_entries():
            self._mount_entry(app, entry)

    def _mount_entry(self, app: FastAPI, entry: AgUiAgentEntry) -> None:
        config = self._container.get(AgUiConfig)
        self._mount_transport(
            app,
            entry,
            transport="sse",
            path=entry.metadata.sse_path or config.sse_path,
            config=config.model_copy(
                update={"sse_path": entry.metadata.sse_path or config.sse_path}
            ),
            registrar=add_agui_endpoint,
        )
        self._mount_transport(
            app,
            entry,
            transport="http_stream",
            path=entry.metadata.http_stream_path or config.http_stream_path,
            config=config.model_copy(
                update={
                    "http_stream_path": (
                        entry.metadata.http_stream_path or config.http_stream_path
                    )
                }
            ),
            registrar=add_agui_http_stream_endpoint,
        )
        self._mount_transport(
            app,
            entry,
            transport="websocket",
            path=entry.metadata.websocket_path or config.websocket_path,
            config=config.model_copy(
                update={
                    "websocket_path": entry.metadata.websocket_path
                    or config.websocket_path
                }
            ),
            registrar=add_agui_websocket_endpoint,
        )

    def _mount_transport(
        self,
        app: FastAPI,
        entry: AgUiAgentEntry,
        *,
        transport: str,
        path: str,
        config: AgUiConfig,
        registrar: _EndpointRegistrar,
    ) -> None:
        app_id = id(app)
        claim_key = (app_id, transport, path)
        current_agent = self._claimed_paths.get(claim_key)
        if current_agent is not None and current_agent != entry.agent_name:
            raise AgUiEndpointConflictError
        self._claimed_paths[claim_key] = entry.agent_name
        mount_key = (app_id, transport, entry.agent_name)
        if mount_key in self._mounted:
            return
        registrar(
            app,
            run_driver_factory=self._run_driver_factory(entry, config),
            config=config,
        )
        self._mounted.add(mount_key)

    def _run_driver_factory(
        self,
        entry: AgUiAgentEntry,
        config: AgUiConfig,
    ) -> RunDriverFactory:
        def factory(
            core_input: RunAgentInput,
            ag_ui_input: AgUiRunAgentInput,
            accept: str | None,
        ) -> AgUiManagedRunDriver:
            runner_factory = self._container.get(IAgentRunnerFactory)
            server_names = entry.metadata.server_names or None
            return AgUiManagedRunDriver(
                runner_context=runner_factory.open_runner(
                    entry.instance,
                    server_names=server_names,
                ),
                inbound=AgUiInboundRun(
                    ag_ui_input=ag_ui_input,
                    core_input=core_input,
                ),
                agent_id=entry.agent_name,
                config=config,
                accept=accept,
            )

        return factory
