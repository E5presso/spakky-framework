import threading
from asyncio import locks
from asyncio.events import AbstractEventLoop, new_event_loop, set_event_loop
from asyncio.tasks import run_coroutine_threadsafe
from contextvars import ContextVar
from logging import Logger, getLogger
from threading import Thread
from types import MappingProxyType
from typing import Callable, cast, overload
from uuid import UUID, uuid4

from spakky.aop.post_processor import AspectPostProcessor
from spakky.core.constants import CONTEXT_ID, CONTEXT_SCOPE_CACHE
from spakky.core.mro import is_family_with
from spakky.core.types import ObjectT, is_optional, remove_none
from spakky.pod.annotations.lazy import Lazy
from spakky.pod.annotations.order import Order
from spakky.pod.annotations.pod import Pod, PodType
from spakky.pod.annotations.qualifier import Qualifier
from spakky.pod.interfaces.application_context import (
    ApplicationContextAlreadyStartedError,
    ApplicationContextAlreadyStoppedError,
    EventLoopThreadAlreadyStartedInApplicationContextError,
    EventLoopThreadNotStartedInApplicationContextError,
    IApplicationContext,
)
from spakky.pod.interfaces.container import (
    CannotRegisterNonPodObjectError,
    CircularDependencyGraphDetectedError,
    NoSuchPodError,
    NoUniquePodError,
    PodNameAlreadyExistsError,
)
from spakky.pod.interfaces.post_processor import IPostProcessor
from spakky.pod.post_processors.aware_post_processor import (
    ApplicationContextAwareProcessor,
)
from spakky.service.interfaces.service import IAsyncService, IService
from spakky.service.post_processor import ServicePostProcessor

"""Application context managing Pod lifecycle and dependency injection.

This module provides the ApplicationContext class which is the core container
for managing Pods, handling dependency injection, and coordinating services.
"""


class ApplicationContext(IApplicationContext):
    """Container managing Pod instances, dependencies, and application lifecycle.

    ApplicationContext is responsible for:
    - Registering and instantiating Pods with dependency injection
    - Managing Pod scopes (SINGLETON, PROTOTYPE, CONTEXT)
    - Running post-processors on Pod instances
    - Coordinating service lifecycle (start/stop)
    - Managing async event loop for async services
    """

    __logger: Logger
    """Logger for application events and errors."""

    __pods: dict[str, Pod]
    """Registry of all Pods by name."""

    __type_cache: dict[type, set[Pod]]
    """Cache mapping types to Pods for O(1) lookup."""

    __forward_type_map: dict[str, type]
    """Map for resolving forward reference types."""

    __singleton_cache: dict[str, object]
    """Cache of singleton-scoped Pod instances."""

    __context_cache: ContextVar[dict[str, object]]
    """Context-local cache for context-scoped Pods."""

    __post_processors: list[IPostProcessor]
    """List of post-processors applied to Pod instances."""

    __services: list[IService]
    """List of synchronous services."""

    __async_services: list[IAsyncService]
    """List of asynchronous services."""

    __event_loop: AbstractEventLoop | None
    """Event loop for running async services."""

    __event_thread: Thread | None
    """Thread running the event loop."""

    __is_started: bool
    """Whether the context has been started."""

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialize application context.

        Args:
            logger: Optional logger instance. If None, uses root logger.
        """
        self.__logger = logger or getLogger()
        self.__forward_type_map = {}
        self.__pods = {}
        self.__type_cache = {}
        self.__singleton_cache = {}
        self.__context_cache = ContextVar(CONTEXT_SCOPE_CACHE)
        self.__post_processors = []
        self.__services = []
        self.__async_services = []
        self.__event_loop = None
        self.__event_thread = None
        self.__is_started = False
        self.task_stop_event = locks.Event()
        self.thread_stop_event = threading.Event()

    def __resolve_candidate(
        self,
        type_: type,
        name: str | None,
        qualifiers: list[Qualifier],
    ) -> Pod | None:
        """Resolve a Pod candidate matching type, name, and qualifiers.

        Args:
            type_: The type to search for.
            name: Optional name qualifier.
            qualifiers: List of qualifier annotations.

        Returns:
            Matching Pod or None if not found.

        Raises:
            NoUniquePodError: If multiple Pods match without clear qualification.
        """

        def qualify_pod(pod: Pod) -> bool:
            if any(qualifiers):
                return all(qualifier.selector(pod) for qualifier in qualifiers)
            if name is not None:
                return pod.name == name
            return pod.is_primary

        # Use type index for O(1) lookup instead of O(n) iteration
        pods = self.__type_cache.get(type_, set()).copy()
        if len(pods) < 1:
            return None
        if len(pods) > 1:
            pods = {pod for pod in pods if qualify_pod(pod)}
            if len(pods) == 1:
                return pods.pop()
            raise NoUniquePodError(type_, [p.name for p in pods])
        return pods.pop()

    def __instantiate_pod(
        self, pod: Pod, dependency_hierarchy: tuple[type, ...]
    ) -> object:
        """Instantiate a Pod with its dependencies recursively resolved.

        Args:
            pod: The Pod to instantiate.
            dependency_hierarchy: Immutable tuple tracking dependency chain for cycle detection.

        Returns:
            The instantiated and post-processed Pod instance.

        Raises:
            CircularDependencyGraphDetectedError: If circular dependency detected.
        """
        if pod.type_ in dependency_hierarchy:
            raise CircularDependencyGraphDetectedError(
                list(dependency_hierarchy) + [pod.type_]
            )
        new_hierarchy = dependency_hierarchy + (pod.type_,)
        dependencies = {
            name: self.__get_internal(
                type_=remove_none(dependency.type_)
                if is_optional(dependency.type_)
                else dependency.type_,
                name=name,
                dependency_hierarchy=new_hierarchy,
                qualifiers=dependency.qualifiers,
            )
            for name, dependency in pod.dependencies.items()
        }
        instance: object = pod.instantiate(dependencies=dependencies)
        post_processed: object = self.__post_process_pod(instance)
        return post_processed

    def __post_process_pod(self, pod: object) -> object:
        """Apply all registered post-processors to a Pod instance.

        Args:
            pod: The Pod instance to process.

        Returns:
            The post-processed Pod instance.
        """
        for post_processor in self.__post_processors:
            pod = post_processor.post_process(pod)
        return pod

    def __register_post_processors(self) -> None:
        """Register built-in and user-defined post-processors.

        Registers post-processors in order:
        1. ApplicationContextAwareProcessor
        2. AspectPostProcessor
        3. ServicePostProcessor
        4. User-defined IPostProcessor Pods (sorted by @Order)
        """
        self.__add_post_processor(ApplicationContextAwareProcessor(self, self.__logger))
        self.__add_post_processor(AspectPostProcessor(self, self.__logger))
        self.__add_post_processor(ServicePostProcessor(self, self.__logger))

        # Find and sort post-processors efficiently using list comprehension
        post_processors = sorted(
            cast(
                list[IPostProcessor],
                list(self.find(lambda x: IPostProcessor in x.base_types)),
            ),
            key=lambda x: Order.get_or_default(x, Order()).order,
        )
        for post_processor in post_processors:
            self.__add_post_processor(post_processor)

    def __initialize_pods(self) -> None:
        """Eagerly initialize all non-lazy Pods.

        Raises:
            NoSuchPodError: If a Pod cannot be instantiated.
        """
        # Eagerly initialize non-lazy pods using list comprehension for efficiency
        non_lazy_pods = [
            pod for pod in self.__pods.values() if not Lazy.exists(pod.target)
        ]
        for pod in non_lazy_pods:
            if (
                self.__get_internal(type_=pod.type_, name=pod.name) is None
            ):  # pragma: no cover
                raise NoSuchPodError(pod.type_, pod.name)

    def __clear_all(self) -> None:
        self.__pods.clear()
        self.__type_cache.clear()
        self.__forward_type_map.clear()
        self.__singleton_cache.clear()
        self.__post_processors.clear()
        self.__services.clear()
        self.__async_services.clear()

    def __set_singleton_cache(self, pod: Pod, instance: object) -> None:
        if pod.scope == Pod.Scope.SINGLETON:
            self.__singleton_cache[pod.name] = instance

    def __get_singleton_cache(self, pod: Pod) -> object | None:
        return self.__singleton_cache.get(pod.name)

    def __set_context_cache(self, pod: Pod, instance: object) -> None:
        cache = self.__context_cache.get({})
        cache[pod.name] = instance
        self.__context_cache.set(cache)

    def __get_context_cache(self, pod: Pod) -> object | None:
        cache = self.__context_cache.get({})
        cached = cache.get(pod.name)
        return cached

    def __get_internal(
        self,
        type_: type[ObjectT],
        name: str | None,
        dependency_hierarchy: tuple[type, ...] | None = None,
        qualifiers: list[Qualifier] | None = None,
    ) -> ObjectT | None:
        """Internal method to get or create a Pod instance.

        Args:
            type_: The type to resolve.
            name: Optional name qualifier.
            dependency_hierarchy: Immutable tuple for circular dependency detection.
            qualifiers: List of qualifier annotations.

        Returns:
            The resolved Pod instance or None if not found.
        """
        if dependency_hierarchy is None:
            # If dependency_hierarchy is None
            # it means that this is the first call on recursive cycle
            dependency_hierarchy = ()
        if qualifiers is None:
            # If qualifiers is None, it means that no qualifier is specified
            qualifiers = []
        if isinstance(type_, str):  # To support forward references  # pragma: no cover
            if type_ not in self.__forward_type_map:  # pragma: no cover
                return None
            type_ = self.__forward_type_map[type_]  # pragma: no cover

        if is_family_with(type_, Logger):
            return cast(ObjectT, self.__logger)
        pod = self.__resolve_candidate(type_=type_, name=name, qualifiers=qualifiers)
        if pod is None:
            return None

        # Try to hit the cache by scope type of pod
        match pod.scope:
            case Pod.Scope.SINGLETON:
                if (cached := self.__get_singleton_cache(pod)) is not None:
                    return cast(ObjectT, cached)
            case Pod.Scope.CONTEXT:
                if (cached := self.__get_context_cache(pod)) is not None:
                    return cast(ObjectT, cached)
            case Pod.Scope.PROTOTYPE:
                pass

        instance: object = self.__instantiate_pod(
            pod,
            dependency_hierarchy,
        )

        # Cache the instance based on pod scope
        match pod.scope:
            case Pod.Scope.SINGLETON:
                self.__set_singleton_cache(pod, instance)
            case Pod.Scope.CONTEXT:
                self.__set_context_cache(pod, instance)
            case Pod.Scope.PROTOTYPE:
                pass

        return cast(ObjectT, instance)

    def __add_post_processor(self, post_processor: IPostProcessor) -> None:
        self.__post_processors.append(post_processor)

    def __run_event_loop(self, loop: AbstractEventLoop) -> None:
        set_event_loop(loop)
        loop.run_forever()
        loop.close()

    def __start_services(self) -> None:
        """Start all registered sync and async services.

        Raises:
            EventLoopThreadAlreadyStartedInApplicationContextError: If already started.
        """
        if self.__event_loop is not None:  # pragma: no cover
            raise EventLoopThreadAlreadyStartedInApplicationContextError
        if self.__event_thread is not None:  # pragma: no cover
            raise EventLoopThreadAlreadyStartedInApplicationContextError

        self.__event_loop = new_event_loop()
        self.__event_thread = Thread(
            target=self.__run_event_loop,
            args=(self.__event_loop,),
            daemon=True,
        )
        self.__event_thread.start()

        for service in self.__services:
            service.start()

        async def start_async_services() -> None:
            if self.__event_loop is None:  # pragma: no cover
                raise EventLoopThreadNotStartedInApplicationContextError
            for service in self.__async_services:
                await service.start_async()

        run_coroutine_threadsafe(start_async_services(), self.__event_loop).result()

    def __stop_services(self) -> None:
        """Stop all services and shutdown event loop.

        Raises:
            EventLoopThreadNotStartedInApplicationContextError: If not started.
        """
        if self.__event_loop is None:  # pragma: no cover
            raise EventLoopThreadNotStartedInApplicationContextError
        if self.__event_thread is None:  # pragma: no cover
            raise EventLoopThreadNotStartedInApplicationContextError

        for service in self.__services:
            service.stop()

        async def stop_async_services() -> None:
            if self.__event_loop is None:  # pragma: no cover
                raise EventLoopThreadNotStartedInApplicationContextError
            for service in self.__async_services:
                await service.stop_async()

        run_coroutine_threadsafe(stop_async_services(), self.__event_loop).result()
        self.__event_loop.call_soon_threadsafe(
            self.__event_loop.stop  # pyrefly: ignore  # type: ignore
        )
        self.__event_thread.join()
        self.__event_loop = None
        self.__event_thread = None

    @property
    def pods(self) -> dict[str, Pod]:
        """Get read-only view of all registered Pods.

        Returns:
            Read-only mapping proxy of Pod registry (O(1) operation).
        """
        return MappingProxyType(self.__pods)  # type: ignore

    @property
    def is_started(self) -> bool:
        """Check if context has been started.

        Returns:
            True if started.
        """
        return self.__is_started

    def find(self, selector: Callable[[Pod], bool]) -> set[object]:
        """Find all Pod instances matching selector predicate.

        Args:
            selector: Predicate function to filter Pods.

        Returns:
            Set of matching Pod instances.
        """
        # Use set comprehension for optimal filtering and instantiation
        return {
            self.__get_internal(type_=pod.type_, name=pod.name)
            for pod in self.__pods.values()
            if selector(pod)
        }

    def add(self, obj: PodType) -> None:
        """Register a Pod-annotated class or function.

        Args:
            obj: The Pod to register.

        Raises:
            CannotRegisterNonPodObjectError: If obj is not annotated with @Pod.
            PodNameAlreadyExistsError: If Pod name already registered with different ID.
        """
        if not Pod.exists(obj):  # pragma: no cover
            raise CannotRegisterNonPodObjectError(obj)
        pod: Pod = Pod.get(obj)
        if pod.name in self.__pods:
            if self.__pods[pod.name].id == pod.id:  # pragma: no cover
                return
            raise PodNameAlreadyExistsError(pod.name)
        for base_type in pod.base_types:
            self.__forward_type_map[base_type.__name__] = base_type
        self.__pods[pod.name] = pod

        # Update type index for fast lookup
        if pod.type_ not in self.__type_cache:
            self.__type_cache[pod.type_] = set()
        self.__type_cache[pod.type_].add(pod)

        # Also index by all base types for polymorphic lookups
        for base_type in pod.base_types:
            if base_type not in self.__type_cache:
                self.__type_cache[base_type] = set()
            self.__type_cache[base_type].add(pod)

    def add_service(self, service: IService | IAsyncService) -> None:
        """Register a service for lifecycle management.

        Args:
            service: The service to register (sync or async).
        """
        if isinstance(service, IService):
            self.__services.append(service)
        if isinstance(service, IAsyncService):
            self.__async_services.append(service)

    def start(self) -> None:
        """Start the application context.

        Registers post-processors, initializes Pods, and starts services.

        Raises:
            ApplicationContextAlreadyStartedError: If already started.
        """
        if self.__is_started:  # pragma: no cover
            raise ApplicationContextAlreadyStartedError()
        self.__is_started = True
        self.__register_post_processors()
        self.__initialize_pods()
        self.__start_services()

    def stop(self) -> None:
        """Stop the application context and clean up resources.

        Raises:
            ApplicationContextAlreadyStoppedError: If already stopped.
        """
        if not self.__is_started:  # pragma: no cover
            raise ApplicationContextAlreadyStoppedError()
        self.__stop_services()
        self.__clear_all()
        self.__is_started = False

    @overload
    def get(self, type_: type[ObjectT]) -> ObjectT: ...

    @overload
    def get(self, type_: type[ObjectT], name: str) -> ObjectT: ...

    def get(
        self,
        type_: type[ObjectT],
        name: str | None = None,
    ) -> ObjectT | object:
        """Get a Pod instance by type and optional name.

        Args:
            type_: The type to retrieve.
            name: Optional name qualifier.

        Returns:
            The Pod instance.

        Raises:
            NoSuchPodError: If no matching Pod found.
        """
        instance = self.__get_internal(type_=type_, name=name)
        if instance is None:  # pragma: no cover
            raise NoSuchPodError(type_, name)
        return instance

    @overload
    def contains(self, type_: type) -> bool: ...

    @overload
    def contains(self, type_: type, name: str) -> bool: ...

    def contains(self, type_: type, name: str | None = None) -> bool:
        """Check if a Pod is registered.

        Args:
            type_: The type to check.
            name: Optional name qualifier.

        Returns:
            True if matching Pod exists.
        """
        if name is not None:
            return name in self.__pods
        # Use type index for O(1) lookup
        return type_ in self.__type_cache and len(self.__type_cache[type_]) > 0

    def get_context_id(self) -> UUID:
        """Get or create unique ID for current context.

        Returns:
            UUID for this context.
        """
        context = self.__context_cache.get({})
        if CONTEXT_ID not in context:  # pragma: no cover
            context[CONTEXT_ID] = uuid4()
            self.__context_cache.set(context)
        return cast(UUID, context[CONTEXT_ID])

    def clear_context(self) -> None:
        """Clear context-scoped cache for current context."""
        self.__context_cache.set({})
