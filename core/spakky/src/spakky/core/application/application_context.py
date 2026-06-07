import threading
from dataclasses import dataclass
from asyncio import locks
from asyncio.events import AbstractEventLoop, new_event_loop, set_event_loop
from asyncio.tasks import run_coroutine_threadsafe
from contextvars import ContextVar
from threading import RLock, Thread
from time import perf_counter
from types import MappingProxyType, NoneType
from typing import Callable, cast, overload
from uuid import UUID, uuid4

from typing import override

from spakky.core.aop.post_processor import AspectPostProcessor
from spakky.core.application.error import AbstractSpakkyApplicationError
from spakky.core.application.startup_diagnostics import (
    IStartupPhaseRecorder,
    NoOpStartupPhaseRecorder,
    StartupDiagnosticDetail,
    StartupDiagnosticDetails,
)
from spakky.core.common.constants import CONTEXT_ID, CONTEXT_SCOPE_CACHE
from spakky.core.common.types import ObjectT, is_optional, remove_none
from spakky.core.pod.annotations.lazy import Lazy
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import (
    DependencyCollectionKind,
    DependencyInfo,
    Pod,
    PodType,
    UnexpectedDependencyTypeInjectedError,
)
from spakky.core.pod.annotations.qualifier import Qualifier
from spakky.core.pod.annotations.tag import Tag
from spakky.core.pod.binding import PodBinding
from spakky.core.pod.diagnostics import (
    PodCandidateDiagnostic,
    PodDependencyPathNode,
    PodDependencyResolutionDiagnostic,
)
from spakky.core.pod.interfaces.application_context import (
    ApplicationContextAlreadyStartedError,
    ApplicationContextAlreadyStoppedError,
    EventLoopThreadAlreadyStartedInApplicationContextError,
    EventLoopThreadNotStartedInApplicationContextError,
    IApplicationContext,
)
from spakky.core.pod.interfaces.container import (
    CannotRegisterNonPodObjectError,
    CircularDependencyGraphDetectedError,
    InvalidPodBindingError,
    NoSuchPodError,
    NoSuchPodBindingTargetError,
    NoUniquePodError,
    PodNameAlreadyExistsError,
)
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.core.pod.post_processors.aware_post_processor import (
    ApplicationContextAwareProcessor,
)
from spakky.core.service.interfaces.service import IAsyncService, IService
from spakky.core.service.post_processor import ServicePostProcessor

"""Application context managing Pod lifecycle and dependency injection.

This module provides the ApplicationContext class which is the core container
for managing Pods, handling dependency injection, and coordinating services.
"""


class CannotAssignSystemContextIDError(AbstractSpakkyApplicationError):
    """Raised when attempting to override the CONTEXT_ID value."""

    message = f"Cannot override {CONTEXT_ID} value."


STARTUP_PHASE_POST_PROCESSOR_REGISTRATION = "post_processor_registration"
STARTUP_PHASE_INSTANTIATION = "instantiation"
STARTUP_PHASE_POST_PROCESSING = "post_processing"
STARTUP_PHASE_SERVICE_START = "service_start"


@dataclass
class _ApplicationContextStartupMetrics:
    instantiation_attempt_count: int = 0
    instantiation_elapsed_seconds: float = 0
    post_processing_application_count: int = 0
    post_processing_elapsed_seconds: float = 0
    post_processing_exception: BaseException | None = None


class ApplicationContext(IApplicationContext):
    """Container managing Pod instances, dependencies, and application lifecycle.

    ApplicationContext is responsible for:
    - Registering and instantiating Pods with dependency injection
    - Managing Pod scopes (SINGLETON, PROTOTYPE, CONTEXT)
    - Running post-processors on Pod instances
    - Coordinating service lifecycle (start/stop)
    - Managing async event loop for async services
    """

    __pods: dict[str, Pod]
    """Registry of all Pods by name."""

    __tags: set[Tag]
    """Registry of all Tags."""

    __type_cache: dict[type, set[Pod]]
    """Cache mapping types to Pods for O(1) lookup."""

    __bindings: dict[type, PodBinding]
    """Explicit interface-to-implementation binding policies."""

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

    __startup_metrics: _ApplicationContextStartupMetrics | None
    """Startup lifecycle metrics for the active start attempt."""

    def __init__(self) -> None:
        """Initialize application context."""
        self.__forward_type_map = {}
        self.__pods = {}
        self.__tags = set()
        self.__type_cache = {}
        self.__bindings = {}
        self.__singleton_cache = {}
        self.__singleton_lock = RLock()
        self.__shutdown_lock = RLock()
        self.__context_cache = ContextVar(CONTEXT_SCOPE_CACHE)
        self.__post_processors = []
        self.__services = []
        self.__async_services = []
        self.__event_loop = None
        self.__event_thread = None
        self.__is_started = False
        self.__startup_metrics = None
        self.task_stop_event = locks.Event()
        self.thread_stop_event = threading.Event()

    def __type_name(self, type_: object) -> str:
        """Return a stable diagnostic name for a dependency type."""
        if isinstance(type_, type):
            return type_.__name__
        return str(type_)

    def __dependency_path_node(
        self,
        pod: Pod,
        dependency_parameter_name: str | None = None,
        requested_type: object | None = None,
    ) -> PodDependencyPathNode:
        """Create one dependency path node from registered Pod metadata."""
        requested_type_name = (
            None if requested_type is None else self.__type_name(requested_type)
        )
        return PodDependencyPathNode(
            pod_name=pod.name,
            pod_type_name=self.__type_name(pod.type_),
            dependency_parameter_name=dependency_parameter_name,
            requested_type_name=requested_type_name,
        )

    def __dependency_diagnostic(
        self,
        pod: Pod,
        dependency_parameter_name: str | None,
        requested_type: object | None,
        dependency_path: tuple[PodDependencyPathNode, ...],
        candidates: tuple[PodCandidateDiagnostic, ...] = (),
        resolution_hints: tuple[str, ...] = (),
    ) -> PodDependencyResolutionDiagnostic:
        """Build structured diagnostics from the active Pod dependency path."""
        requested_type_name = (
            None if requested_type is None else self.__type_name(requested_type)
        )
        return PodDependencyResolutionDiagnostic(
            failed_pod_name=pod.name,
            failed_pod_type_name=self.__type_name(pod.type_),
            dependency_parameter_name=dependency_parameter_name,
            requested_type_name=requested_type_name,
            path=dependency_path,
            candidates=candidates,
            resolution_hints=resolution_hints,
        )

    def __startup_diagnostic_details(
        self,
        exception: BaseException,
    ) -> StartupDiagnosticDetails:
        """Convert dependency resolution diagnostics into startup report details."""
        dependency_diagnostic: PodDependencyResolutionDiagnostic | None = None
        if isinstance(exception, UnexpectedDependencyTypeInjectedError):
            dependency_diagnostic = exception.dependency_diagnostic
        if isinstance(exception, NoUniquePodError):
            dependency_diagnostic = exception.dependency_diagnostic
        if isinstance(exception, CircularDependencyGraphDetectedError):
            dependency_diagnostic = exception.dependency_diagnostic
        if dependency_diagnostic is None:
            return ()
        return tuple(
            StartupDiagnosticDetail(key=key, value=value)
            for key, value in dependency_diagnostic.as_detail_pairs()
        )

    def __candidate_diagnostics(
        self,
        pods: set[Pod],
    ) -> tuple[PodCandidateDiagnostic, ...]:
        """Return stable ambiguity diagnostics for candidate Pods."""
        return tuple(
            PodCandidateDiagnostic(
                pod_name=pod.name,
                pod_type_name=self.__type_name(pod.type_),
                is_primary=pod.is_primary,
            )
            for pod in sorted(pods, key=lambda candidate: candidate.name)
        )

    def __ambiguity_hints(
        self, dependency_parameter_name: str | None
    ) -> tuple[str, ...]:
        """Return resolution hints for a single dependency ambiguity."""
        hints = (
            "add Annotated[T, Qualifier(...)] to select one candidate",
            "register ApplicationContext.bind(PodBinding(...)) from application config",
            "mark exactly one candidate with @Primary",
        )
        if dependency_parameter_name is None:
            return hints + ("call get(type_, name=...) for an explicit Pod name",)
        return hints + (
            "rename the dependency parameter to one candidate Pod name as legacy fallback",
        )

    def __ambiguity_diagnostic(
        self,
        requester_pod: Pod | None,
        dependency_parameter_name: str | None,
        requested_type: type,
        dependency_path: tuple[PodDependencyPathNode, ...],
        candidates: tuple[PodCandidateDiagnostic, ...],
        resolution_hints: tuple[str, ...],
    ) -> PodDependencyResolutionDiagnostic | None:
        """Build dependency diagnostics when ambiguity occurs during injection."""
        if requester_pod is None:
            return None
        return self.__dependency_diagnostic(
            pod=requester_pod,
            dependency_parameter_name=dependency_parameter_name,
            requested_type=requested_type,
            dependency_path=dependency_path,
            candidates=candidates,
            resolution_hints=resolution_hints,
        )

    def __binding_target_count(self, binding: PodBinding) -> int:
        """Return how many target selectors a binding specifies."""
        count = 0
        if binding.implementation_type is not None:
            count += 1
        if binding.implementation_name is not None:
            count += 1
        return count

    def __validate_binding(self, binding: PodBinding) -> None:
        """Validate binding shape without requiring Pods to be registered yet."""
        if self.__binding_target_count(binding) != 1:
            raise InvalidPodBindingError

    def __resolve_binding_candidate(
        self,
        type_: type,
        pods: set[Pod],
    ) -> Pod | None:
        """Resolve an explicit binding for this requested type, when configured."""
        binding = self.__bindings.get(type_)
        if binding is None:
            return None
        if binding.implementation_name is not None:
            named = {pod for pod in pods if pod.name == binding.implementation_name}
            if len(named) == 1:
                return named.pop()
            raise NoSuchPodBindingTargetError(binding)
        typed = {pod for pod in pods if pod.type_ == binding.implementation_type}
        if len(typed) == 1:
            return typed.pop()
        raise NoSuchPodBindingTargetError(binding)

    def __resolve_collection_candidates(
        self,
        type_: type,
        qualifiers: list[Qualifier],
    ) -> tuple[Pod, ...]:
        """Resolve all collection dependency candidates in stable Pod name order."""
        pods = self.__type_cache.get(type_, set()).copy()
        if qualifiers:
            pods = {
                pod
                for pod in pods
                if all(qualifier.selector(pod) for qualifier in qualifiers)
            }
        return tuple(sorted(pods, key=lambda pod: pod.name))

    def __resolve_candidate(
        self,
        type_: type,
        name: str | None,
        qualifiers: list[Qualifier],
        name_is_dependency_parameter: bool,
        requester_pod: Pod | None,
        dependency_path: tuple[PodDependencyPathNode, ...],
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

        # Use type index for O(1) lookup instead of O(n) iteration
        pods = self.__type_cache.get(type_, set()).copy()
        if not pods:
            return None

        if qualifiers:
            qualified = {
                pod
                for pod in pods
                if all(qualifier.selector(pod) for qualifier in qualifiers)
            }
            if len(qualified) == 1:
                return qualified.pop()
            if not qualified:
                return None
            candidates = self.__candidate_diagnostics(qualified)
            resolution_hints = self.__ambiguity_hints(name)
            raise NoUniquePodError(
                type_,
                candidates,
                self.__ambiguity_diagnostic(
                    requester_pod=requester_pod,
                    dependency_parameter_name=name,
                    requested_type=type_,
                    dependency_path=dependency_path,
                    candidates=candidates,
                    resolution_hints=resolution_hints,
                ),
                resolution_hints,
            )

        if name is not None and not name_is_dependency_parameter:
            named = {pod for pod in pods if pod.name == name}
            if len(named) == 1:
                return named.pop()
            if not named:
                return None

        if binding_candidate := self.__resolve_binding_candidate(type_, pods):
            return binding_candidate

        # Fast path after explicit selectors and binding policy are honored.
        if len(pods) == 1:
            return next(iter(pods))

        primary = {pod for pod in pods if pod.is_primary}
        if len(primary) == 1:
            return primary.pop()
        if len(primary) > 1:
            candidates = self.__candidate_diagnostics(primary)
            resolution_hints = self.__ambiguity_hints(name)
            raise NoUniquePodError(
                type_,
                candidates,
                self.__ambiguity_diagnostic(
                    requester_pod=requester_pod,
                    dependency_parameter_name=name,
                    requested_type=type_,
                    dependency_path=dependency_path,
                    candidates=candidates,
                    resolution_hints=resolution_hints,
                ),
                resolution_hints,
            )

        if name is not None and name_is_dependency_parameter:
            legacy_named = {pod for pod in pods if pod.name == name}
            if len(legacy_named) == 1:
                return legacy_named.pop()

        candidates = self.__candidate_diagnostics(pods)
        resolution_hints = self.__ambiguity_hints(name)
        raise NoUniquePodError(
            type_,
            candidates,
            self.__ambiguity_diagnostic(
                requester_pod=requester_pod,
                dependency_parameter_name=name,
                requested_type=type_,
                dependency_path=dependency_path,
                candidates=candidates,
                resolution_hints=resolution_hints,
            ),
            resolution_hints,
        )

    def __instantiate_pod(
        self,
        pod: Pod,
        dependency_hierarchy: tuple[type, ...],
        dependency_path: tuple[PodDependencyPathNode, ...],
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
            circular_path = dependency_path + (self.__dependency_path_node(pod),)
            last_node = dependency_path[-1] if dependency_path else None
            raise CircularDependencyGraphDetectedError(
                list(dependency_hierarchy) + [pod.type_],
                dependency_diagnostic=self.__dependency_diagnostic(
                    pod=pod,
                    dependency_parameter_name=None
                    if last_node is None
                    else last_node.dependency_parameter_name,
                    requested_type=None
                    if last_node is None
                    else last_node.requested_type_name,
                    dependency_path=circular_path,
                ),
            )
        new_hierarchy = dependency_hierarchy + (pod.type_,)
        dependencies: dict[str, object | None] = {}
        for name, dependency in pod.dependencies.items():
            requested_type = (
                remove_none(dependency.type_)
                if is_optional(dependency.type_)
                else dependency.type_
            )
            current_path = dependency_path + (
                self.__dependency_path_node(
                    pod=pod,
                    dependency_parameter_name=name,
                    requested_type=requested_type,
                ),
            )
            if dependency.collection_kind is None:
                resolved_dependency = self.__get_internal(
                    type_=remove_none(dependency.type_)
                    if is_optional(dependency.type_)
                    else dependency.type_,
                    name=name,
                    dependency_hierarchy=new_hierarchy,
                    dependency_path=current_path,
                    qualifiers=dependency.qualifiers,
                    name_is_dependency_parameter=True,
                    requester_pod=pod,
                )
            else:
                resolved_dependency = self.__resolve_collection_dependency(
                    dependency=dependency,
                    dependency_hierarchy=new_hierarchy,
                    dependency_path=current_path,
                )
            if (
                resolved_dependency is None
                and not dependency.has_default
                and not dependency.is_optional
            ):
                raise UnexpectedDependencyTypeInjectedError(
                    pod.type_,
                    {
                        "name": name,
                        "expected": dependency.type_,
                        "actual": NoneType,
                    },
                    dependency_diagnostic=self.__dependency_diagnostic(
                        pod=pod,
                        dependency_parameter_name=name,
                        requested_type=requested_type,
                        dependency_path=current_path,
                    ),
                )
            dependencies[name] = resolved_dependency
        started_at = perf_counter()
        try:
            instance: object = pod.instantiate(dependencies=dependencies)
        except BaseException:
            self.__record_instantiation_attempt(perf_counter() - started_at)
            raise
        self.__record_instantiation_attempt(perf_counter() - started_at)
        post_processed: object = self.__post_process_pod(instance)
        return post_processed

    def __get_pod_instance(
        self,
        pod: Pod,
        dependency_hierarchy: tuple[type, ...],
        dependency_path: tuple[PodDependencyPathNode, ...],
    ) -> object:
        """Get or create an instance for an already resolved Pod candidate."""
        match pod.scope:
            case Pod.Scope.SINGLETON:
                if (cached := self.__get_singleton_cache(pod)) is not None:
                    return cached
                with self.__singleton_lock:
                    if (cached := self.__singleton_cache.get(pod.name)) is not None:
                        return cached
                    instance = self.__instantiate_pod(
                        pod,
                        dependency_hierarchy,
                        dependency_path,
                    )
                    self.__set_singleton_cache(pod, instance)
                    return instance
            case Pod.Scope.CONTEXT:
                if (cached := self.__get_context_cache(pod)) is not None:
                    return cached

        instance = self.__instantiate_pod(
            pod,
            dependency_hierarchy,
            dependency_path,
        )

        match pod.scope:
            case Pod.Scope.CONTEXT:
                self.__set_context_cache(pod, instance)

        return instance

    def __resolve_collection_dependency(
        self,
        dependency: DependencyInfo,
        dependency_hierarchy: tuple[type, ...],
        dependency_path: tuple[PodDependencyPathNode, ...],
    ) -> object | None:
        """Resolve list/tuple/dict dependency injection without single ambiguity."""
        pods = self.__resolve_collection_candidates(
            type_=dependency.type_,
            qualifiers=dependency.qualifiers,
        )
        if not pods:
            return None

        instances = [
            self.__get_pod_instance(
                pod=pod,
                dependency_hierarchy=dependency_hierarchy,
                dependency_path=dependency_path,
            )
            for pod in pods
        ]
        match dependency.collection_kind:
            case DependencyCollectionKind.LIST:
                return instances
            case DependencyCollectionKind.TUPLE:
                return tuple(instances)
            case DependencyCollectionKind.DICT:
                return {
                    pod.name: instance
                    for pod, instance in zip(pods, instances, strict=True)
                }
        return None

    def __record_instantiation_attempt(self, elapsed_seconds: float) -> None:
        if self.__startup_metrics is None:
            return
        self.__startup_metrics.instantiation_elapsed_seconds += elapsed_seconds

    def __post_process_pod(self, pod: object) -> object:
        """Apply all registered post-processors to a Pod instance.

        Args:
            pod: The Pod instance to process.

        Returns:
            The post-processed Pod instance.
        """
        for post_processor in self.__post_processors:
            started_at = perf_counter()
            try:
                pod = post_processor.post_process(pod)
            except BaseException as e:
                self.__record_post_processing_attempt(perf_counter() - started_at, e)
                raise
            self.__record_post_processing_attempt(perf_counter() - started_at)
        return pod

    def __record_post_processing_attempt(
        self,
        elapsed_seconds: float,
        exception: BaseException | None = None,
    ) -> None:
        if self.__startup_metrics is None:
            return
        self.__startup_metrics.post_processing_application_count += 1
        self.__startup_metrics.post_processing_elapsed_seconds += elapsed_seconds
        if exception is not None:
            self.__startup_metrics.post_processing_exception = exception

    def __register_post_processors(self) -> None:
        """Register built-in and user-defined post-processors.

        Registers post-processors in order:
        1. ApplicationContextAwareProcessor
        2. AspectPostProcessor
        3. ServicePostProcessor
        4. User-defined IPostProcessor Pods (sorted by @Order)
        """
        self.__add_post_processor(ApplicationContextAwareProcessor(self))
        self.__add_post_processor(AspectPostProcessor(self))
        self.__add_post_processor(ServicePostProcessor(self))

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
            if self.__startup_metrics is not None:
                self.__startup_metrics.instantiation_attempt_count += 1
            if (
                self.__get_internal(type_=pod.type_, name=pod.name) is None
            ):  # pragma: no cover - coverage boundary
                raise NoSuchPodError(pod.type_, pod.name)

    def __clear_all(self) -> None:
        self.__pods.clear()
        self.__type_cache.clear()
        self.__bindings.clear()
        self.__forward_type_map.clear()
        with self.__singleton_lock:
            self.__singleton_cache.clear()
        self.__post_processors.clear()
        self.__services.clear()
        self.__async_services.clear()

    def __rollback_failed_start(
        self,
        original_service_count: int,
        original_async_service_count: int,
        started_services: list[IService],
        started_async_services: list[IAsyncService],
    ) -> None:
        event_loop = self.__event_loop
        event_thread = self.__event_thread
        for service in reversed(started_services):
            service.stop()
        if event_loop is not None and started_async_services:

            async def stop_started_async_services() -> None:
                for service in reversed(started_async_services):
                    await service.stop_async()

            run_coroutine_threadsafe(stop_started_async_services(), event_loop).result()
        if event_loop is not None:
            event_loop.call_soon_threadsafe(event_loop.stop)  # type: ignore[arg-type]  # stop() is valid callback
        if event_thread is not None:
            event_thread.join()
        self.__event_loop = None
        self.__event_thread = None
        with self.__singleton_lock:
            self.__singleton_cache.clear()
        self.clear_context()
        self.__post_processors.clear()
        del self.__services[original_service_count:]
        del self.__async_services[original_async_service_count:]
        self.__is_started = False

    def __set_singleton_cache(self, pod: Pod, instance: object) -> None:
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
        dependency_path: tuple[PodDependencyPathNode, ...] | None = None,
        qualifiers: list[Qualifier] | None = None,
        name_is_dependency_parameter: bool = False,
        requester_pod: Pod | None = None,
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
        if dependency_path is None:
            dependency_path = ()
        if qualifiers is None:
            # If qualifiers is None, it means that no qualifier is specified
            qualifiers = []
        if isinstance(
            type_, str
        ):  # To support forward references  # pragma: no cover - coverage boundary
            if (
                type_ not in self.__forward_type_map
            ):  # pragma: no cover - coverage boundary
                return None
            type_ = self.__forward_type_map[
                type_
            ]  # pragma: no cover - coverage boundary

        pod = self.__resolve_candidate(
            type_=type_,
            name=name,
            qualifiers=qualifiers,
            name_is_dependency_parameter=name_is_dependency_parameter,
            requester_pod=requester_pod,
            dependency_path=dependency_path,
        )
        if pod is None:
            return None

        return cast(
            ObjectT,
            self.__get_pod_instance(
                pod=pod,
                dependency_hierarchy=dependency_hierarchy,
                dependency_path=dependency_path,
            ),
        )

    def __add_post_processor(self, post_processor: IPostProcessor) -> None:
        self.__post_processors.append(post_processor)

    def __run_event_loop(self, loop: AbstractEventLoop) -> None:
        set_event_loop(loop)
        loop.run_forever()
        loop.close()

    def __start_services(
        self,
        started_services: list[IService],
        started_async_services: list[IAsyncService],
    ) -> None:
        """Start all registered sync and async services.

        Raises:
            EventLoopThreadAlreadyStartedInApplicationContextError: If already started.
        """
        if self.__event_loop is not None:  # pragma: no cover - coverage boundary
            raise EventLoopThreadAlreadyStartedInApplicationContextError
        if self.__event_thread is not None:  # pragma: no cover - coverage boundary
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
            started_services.append(service)

        async def start_async_services() -> None:
            if self.__event_loop is None:  # pragma: no cover - coverage boundary
                raise EventLoopThreadNotStartedInApplicationContextError
            for service in self.__async_services:
                await service.start_async()
                started_async_services.append(service)

        run_coroutine_threadsafe(start_async_services(), self.__event_loop).result()

    def __stop_services(self) -> None:
        """Stop all services and shutdown event loop.

        Raises:
            EventLoopThreadNotStartedInApplicationContextError: If not started.
        """
        if self.__event_loop is None:  # pragma: no cover - coverage boundary
            raise EventLoopThreadNotStartedInApplicationContextError
        if self.__event_thread is None:  # pragma: no cover - coverage boundary
            raise EventLoopThreadNotStartedInApplicationContextError

        # Store references to avoid race condition with concurrent stop() calls
        event_loop = self.__event_loop
        event_thread = self.__event_thread

        for service in self.__services:
            service.stop()

        async def stop_async_services() -> None:
            for service in self.__async_services:
                await service.stop_async()

        run_coroutine_threadsafe(stop_async_services(), event_loop).result()
        event_loop.call_soon_threadsafe(event_loop.stop)  # type: ignore[arg-type]  # stop() is valid callback
        event_thread.join()

        # Clear references after thread has joined
        self.__event_loop = None
        self.__event_thread = None

    @property
    @override
    def pods(self) -> dict[str, Pod]:
        """Get read-only view of all registered Pods.

        Returns:
            Read-only mapping proxy of Pod registry (O(1) operation).
        """
        return MappingProxyType(self.__pods)  # type: ignore[return-value]  # MappingProxyType is dict-compatible

    @property
    @override
    def tags(self) -> frozenset[Tag]:
        """Get read-only view of all registered Tags.

        Returns:
            Read-only frozenset of Tag registry (O(1) operation).
        """
        return frozenset(self.__tags)

    @property
    @override
    def is_started(self) -> bool:
        """Check if context has been started.

        Returns:
            True if started.
        """
        return self.__is_started

    @override
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

    @override
    def add(self, obj: PodType) -> None:
        """Register a Pod-annotated class or function.

        Args:
            obj: The Pod to register.

        Raises:
            CannotRegisterNonPodObjectError: If obj is not annotated with @Pod.
            PodNameAlreadyExistsError: If Pod name already registered with different ID.
        """
        if not Pod.exists(obj):  # pragma: no cover - coverage boundary
            raise CannotRegisterNonPodObjectError(obj)
        pod: Pod = Pod.get(obj)
        if pod.name in self.__pods:
            # 같은 ID의 Pod 재등록은 add() 호출 패턴상 발생하지 않음
            if (
                self.__pods[pod.name].id == pod.id
            ):  # pragma: no cover - coverage boundary
                return
            raise PodNameAlreadyExistsError(pod.name)
        for base_type in pod.base_types:
            self.__forward_type_map[base_type.__name__] = base_type
        self.__pods[pod.name] = pod

        # Update type index for fast lookup
        # pod.type_은 클래스 자체이므로 같은 타입 두 Pod은 이름 충돌로 위에서 차단됨
        if (
            pod.type_ not in self.__type_cache
        ):  # pragma: no branch - same-type pod names are rejected above
            self.__type_cache[pod.type_] = set()
        self.__type_cache[pod.type_].add(pod)

        # Also index by all base types for polymorphic lookups
        for base_type in pod.base_types:
            if base_type not in self.__type_cache:
                self.__type_cache[base_type] = set()
            self.__type_cache[base_type].add(pod)

    @override
    def bind(self, binding: PodBinding) -> None:
        """Register an explicit interface-to-implementation binding policy."""
        self.__validate_binding(binding)
        self.__bindings[binding.interface] = binding

    @override
    def bind_to_type(self, interface: type, implementation: type) -> None:
        """Bind an interface to a concrete implementation type."""
        self.bind(PodBinding(interface=interface, implementation_type=implementation))

    @override
    def bind_to_name(self, interface: type, name: str) -> None:
        """Bind an interface to a registered Pod name."""
        self.bind(PodBinding(interface=interface, implementation_name=name))

    @override
    def add_service(self, service: IService | IAsyncService) -> None:
        """Register a service for lifecycle management.

        Args:
            service: The service to register (sync or async).
        """
        if isinstance(service, IService):
            self.__services.append(service)
        if isinstance(service, IAsyncService):
            self.__async_services.append(service)

    @override
    def start(
        self,
        startup_phase_recorder: IStartupPhaseRecorder | None = None,
    ) -> None:
        """Start the application context.

        Registers post-processors, initializes Pods, and starts services.

        Raises:
            ApplicationContextAlreadyStartedError: If already started.
        """
        if self.__is_started:  # pragma: no cover - coverage boundary
            raise ApplicationContextAlreadyStartedError()
        recorder = (
            startup_phase_recorder
            if startup_phase_recorder is not None
            else NoOpStartupPhaseRecorder()
        )
        original_service_count = len(self.__services)
        original_async_service_count = len(self.__async_services)
        started_services: list[IService] = []
        started_async_services: list[IAsyncService] = []
        self.__is_started = True
        try:
            with recorder.record_phase(
                phase_name=STARTUP_PHASE_POST_PROCESSOR_REGISTRATION
            ) as phase:
                self.__register_post_processors()
                phase.set_processed_count(len(self.__post_processors))

            startup_metrics = _ApplicationContextStartupMetrics()
            self.__startup_metrics = startup_metrics
            try:
                self.__initialize_pods()
            except BaseException as e:
                if startup_metrics.post_processing_exception is None:
                    recorder.record_failure(
                        phase_name=STARTUP_PHASE_INSTANTIATION,
                        elapsed_seconds=startup_metrics.instantiation_elapsed_seconds,
                        exception=e,
                        processed_count=startup_metrics.instantiation_attempt_count,
                        diagnostic_details=self.__startup_diagnostic_details(e),
                    )
                else:
                    recorder.record_success(
                        phase_name=STARTUP_PHASE_INSTANTIATION,
                        elapsed_seconds=startup_metrics.instantiation_elapsed_seconds,
                        processed_count=startup_metrics.instantiation_attempt_count,
                    )
                    recorder.record_failure(
                        phase_name=STARTUP_PHASE_POST_PROCESSING,
                        elapsed_seconds=startup_metrics.post_processing_elapsed_seconds,
                        exception=startup_metrics.post_processing_exception,
                        processed_count=startup_metrics.post_processing_application_count,
                        diagnostic_details=self.__startup_diagnostic_details(
                            startup_metrics.post_processing_exception
                        ),
                    )
                raise

            recorder.record_success(
                phase_name=STARTUP_PHASE_INSTANTIATION,
                elapsed_seconds=startup_metrics.instantiation_elapsed_seconds,
                processed_count=startup_metrics.instantiation_attempt_count,
            )
            recorder.record_success(
                phase_name=STARTUP_PHASE_POST_PROCESSING,
                elapsed_seconds=startup_metrics.post_processing_elapsed_seconds,
                processed_count=startup_metrics.post_processing_application_count,
            )

            service_start_count = len(self.__services) + len(self.__async_services)
            with recorder.record_phase(
                phase_name=STARTUP_PHASE_SERVICE_START,
                processed_count=service_start_count,
            ):
                self.__start_services(started_services, started_async_services)
        except BaseException:
            self.__rollback_failed_start(
                original_service_count=original_service_count,
                original_async_service_count=original_async_service_count,
                started_services=started_services,
                started_async_services=started_async_services,
            )
            raise
        finally:
            self.__startup_metrics = None

    @override
    def stop(self) -> None:
        """Stop the application context and clean up resources.

        Thread-safe: Multiple concurrent calls to stop() are serialized.

        Raises:
            ApplicationContextAlreadyStoppedError: If already stopped.
        """
        with self.__shutdown_lock:
            if not self.__is_started:  # pragma: no cover - coverage boundary
                raise ApplicationContextAlreadyStoppedError()
            self.__stop_services()
            self.__clear_all()
            self.__is_started = False

    @overload
    def get(self, type_: type[ObjectT]) -> ObjectT: ...

    @overload
    def get(self, type_: type[ObjectT], name: str) -> ObjectT: ...

    @override
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
        if instance is None:  # pragma: no cover - coverage boundary
            raise NoSuchPodError(type_, name)
        return instance

    @overload
    def get_or_none(self, type_: type[ObjectT]) -> ObjectT | None: ...

    @overload
    def get_or_none(self, type_: type[ObjectT], name: str) -> ObjectT | None: ...

    @override
    def get_or_none(
        self,
        type_: type[ObjectT],
        name: str | None = None,
    ) -> ObjectT | None:
        """Get a Pod instance by type and optional name, or None if not found.

        Args:
            type_: The type to retrieve.
            name: Optional name qualifier.

        Returns:
            The Pod instance, or None if no matching Pod found.
        """
        return self.__get_internal(type_=type_, name=name)

    @overload
    def contains(self, type_: type) -> bool: ...

    @overload
    def contains(self, type_: type, name: str) -> bool: ...

    @override
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

    @override
    def register_tag(self, tag: Tag) -> None:
        """Register a Tag instance.

        Args:
            tag: The Tag to register.
        """
        self.__tags.add(tag)

    @override
    def contains_tag(self, tag: Tag) -> bool:
        """Check if a Tag is registered.

        Args:
            tag: The Tag to check.

        Returns:
            True if Tag is registered.
        """
        return tag in self.__tags

    @override
    def list_tags(
        self, selector: Callable[[Tag], bool] | None = None
    ) -> frozenset[Tag]:
        """List registered Tags, optionally filtered by selector.

        Args:
            selector: Optional predicate to filter Tags.
        Returns:
            Set of matching Tags.
        """
        if selector is None:
            return frozenset(self.__tags)
        return frozenset(tag for tag in self.__tags if selector(tag))

    @override
    def get_context_id(self) -> UUID:
        """Get or create unique ID for current context.

        Returns:
            UUID for this context.
        """
        context = self.__context_cache.get({})
        if CONTEXT_ID not in context:  # pragma: no cover - coverage boundary
            context[CONTEXT_ID] = uuid4()
            self.__context_cache.set(context)
        return cast(UUID, context[CONTEXT_ID])

    @override
    def get_context_value(self, key: str) -> object | None:
        """Get a value from the context-scoped cache.

        Args:
            key: The key to retrieve.

        Returns:
            The cached value, or None if not found.
        """
        if key == CONTEXT_ID:
            return self.get_context_id()
        context = self.__context_cache.get({})
        return context.get(key)

    @override
    def set_context_value(self, key: str, value: object) -> None:
        """Set a value in the context-scoped cache.

        Args:
            key: The key to set.
            value: The value to store.
        """
        if key == CONTEXT_ID:  # pragma: no cover - coverage boundary
            raise CannotAssignSystemContextIDError
        context = self.__context_cache.get({})
        context[key] = value
        self.__context_cache.set(context)

    @override
    def clear_context(self) -> None:
        """Clear context-scoped cache for current context."""
        self.__context_cache.set({})
