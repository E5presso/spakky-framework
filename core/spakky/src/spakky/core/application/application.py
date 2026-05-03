"""Main application class for bootstrapping the Spakky framework.

This module provides the SpakkyApplication class which serves as the entry point
for configuring and starting a Spakky application with DI/IoC and AOP support.
"""

import inspect
from importlib.metadata import entry_points
from pathlib import Path
from types import FunctionType, ModuleType
from typing import Callable, Self

from spakky.core.application.discovery_manifest import (
    DISCOVERY_MANIFEST_DETAIL_KEY,
    DiscoveryManifest,
    DiscoveryManifestCandidate,
    DiscoveryManifestDecision,
    DiscoveryManifestFingerprint,
    DiscoveryManifestStore,
    default_discovery_manifest_path,
)
from spakky.core.application.error import AbstractSpakkyApplicationError
from spakky.core.application.plugin import Plugin
from spakky.core.application.startup_diagnostics import (
    ActiveStartupPhaseRecorder,
    IStartupPhaseRecorder,
    NoOpStartupPhaseRecorder,
    StartupDiagnosticDetail,
    StartupReport,
)
from spakky.core.common.constants import PLUGIN_PATH
from spakky.core.common.importing import (
    Module,
    ensure_importable,
    is_package,
    list_modules,
    list_objects,
    resolve_module,
)
from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.annotations.tag import Tag
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer

STARTUP_PHASE_LOAD_PLUGINS = "load_plugins"
STARTUP_PHASE_SCAN = "scan"
STARTUP_PHASE_REGISTRATION = "registration"


@immutable
class _DiscoveryManifestHit:
    """Resolved DiscoveryManifest hit candidates."""

    decision: DiscoveryManifestDecision
    """Final manifest decision after object resolution."""

    objects: tuple[PodType, ...]
    """Resolved Pod or Tag objects."""


class CannotDetermineScanPathError(AbstractSpakkyApplicationError):
    """Raised when the scan path cannot be automatically determined."""

    message = "Cannot determine scan path. Please specify the path explicitly."


class SpakkyApplication:
    """Main application class for bootstrapping Spakky framework.

    Provides a fluent API for configuring dependency injection, aspect-oriented
    programming, plugin loading, and component scanning.
    """

    _application_context: IApplicationContext
    """The application context managing all Pods and their lifecycle."""

    _startup_phase_recorder: IStartupPhaseRecorder
    """Recorder used by startup pipeline diagnostics."""

    _discovery_manifest_path: Path | None
    """Opt-in DiscoveryManifest path for scan result reuse."""

    @property
    def container(self) -> IContainer:
        """Get the IoC container.

        Returns:
            The application's dependency injection container.
        """
        return self._application_context

    @property
    def application_context(self) -> IApplicationContext:
        """Get the application context.

        Returns:
            The application's context managing Pods and lifecycle.
        """
        return self._application_context

    @property
    def startup_phase_recorder(self) -> IStartupPhaseRecorder:
        """Get the startup phase recorder.

        Returns:
            Active or no-op startup phase recorder.
        """
        return self._startup_phase_recorder

    @property
    def startup_report(self) -> StartupReport:
        """Get the startup diagnostics report.

        Returns:
            Startup report backing the current phase recorder.
        """
        return self._startup_phase_recorder.report

    @property
    def discovery_manifest_path(self) -> Path | None:
        """Get the configured DiscoveryManifest path.

        Returns:
            Manifest path when reuse is enabled, otherwise None.
        """
        return self._discovery_manifest_path

    def __init__(self, application_context: IApplicationContext) -> None:
        """Initialize the Spakky application.

        Args:
            application_context: The application context to manage Pods.
        """
        self._application_context = application_context
        self._startup_phase_recorder = NoOpStartupPhaseRecorder()
        self._discovery_manifest_path = None

    def enable_startup_diagnostics(self) -> Self:
        """Enable startup diagnostics with an active phase recorder.

        Returns:
            Self for method chaining.
        """
        self._startup_phase_recorder = ActiveStartupPhaseRecorder()
        return self

    def enable_discovery_manifest(self, path: Path | str | None = None) -> Self:
        """Enable reusable scan discovery manifests.

        Args:
            path: Explicit manifest path. None uses a deterministic project cache path.

        Returns:
            Self for method chaining.
        """
        self._discovery_manifest_path = (
            default_discovery_manifest_path() if path is None else Path(path)
        )
        return self

    def add(self, obj: PodType) -> Self:
        """Register a class or function in the application.

        - If the object has a @Pod annotation, it is registered in the container.
        - If the object has a @Tag annotation, the tag is registered in the tag registry.

        Args:
            obj: The class or function to register.

        Returns:
            Self for method chaining.
        """
        if Pod.exists(obj):
            self._application_context.add(obj)
        if Tag.exists(obj):
            tag = Tag.get(obj)
            self._application_context.register_tag(tag)
        return self

    def scan(
        self,
        path: Module | None = None,
        exclude: set[Module] | None = None,
    ) -> Self:
        """Scan a module for Pod-annotated classes and functions.

        When path is None, automatically detects the caller's package and scans it.
        If the caller's package is not importable (e.g., in Docker environments where
        the application root is not in sys.path), the parent directory is automatically
        added to sys.path to enable package discovery.

        Args:
            path: Module or package to scan. If None, scans the caller's package.
            exclude: Set of modules to exclude from scanning.

        Returns:
            Self for method chaining.

        Raises:
            CannotDetermineScanPathError: If path is None and cannot determine caller's package.
        """
        modules: set[ModuleType]
        caller_module: ModuleType | None = None
        manifest_decision: DiscoveryManifestDecision | None = None
        manifest_fingerprint: DiscoveryManifestFingerprint | None = None
        discovery_candidates: list[DiscoveryManifestCandidate] = []
        discovered_objects: tuple[PodType, ...] = ()
        with self._startup_phase_recorder.record_phase(
            phase_name=STARTUP_PHASE_SCAN
        ) as scan_phase:
            if path is None:  # pragma: no cover - coverage boundary
                caller_frame = inspect.stack()[1]
                caller_file = caller_frame.filename
                caller_dir = Path(caller_file).parent

                # Check if caller is inside a package (has __init__.py)
                if not (caller_dir / "__init__.py").exists():
                    raise CannotDetermineScanPathError

                # Ensure the package is importable (adds to sys.path if needed)
                ensure_importable(caller_dir)

                try:
                    path = resolve_module(caller_dir.name)
                except ImportError as e:
                    raise CannotDetermineScanPathError from e

                caller_module = inspect.getmodule(caller_frame[0])

            if exclude is None:
                exclude = {caller_module} if caller_module else set()
            if self._discovery_manifest_path is not None:
                manifest_fingerprint = DiscoveryManifestFingerprint.from_scan_input(
                    path=path,
                    exclude=exclude,
                )
                manifest_load_result = DiscoveryManifestStore(
                    self._discovery_manifest_path
                ).load(manifest_fingerprint)
                manifest_decision = manifest_load_result.decision
                if manifest_load_result.manifest is not None:
                    manifest_hit = self._resolve_manifest_hit(
                        manifest_load_result.manifest.candidates
                    )
                    manifest_decision = manifest_hit.decision
                    discovered_objects = manifest_hit.objects
                    if manifest_decision is DiscoveryManifestDecision.HIT:
                        modules = {
                            resolve_module(module_name)
                            for module_name in manifest_load_result.manifest.module_names
                        }
                    else:
                        modules = self._discover_modules(path, exclude)
                else:
                    modules = self._discover_modules(path, exclude)
                scan_phase.set_diagnostic_details(
                    (
                        StartupDiagnosticDetail(
                            key=DISCOVERY_MANIFEST_DETAIL_KEY,
                            value=manifest_decision.value,
                        ),
                    )
                )
            else:
                modules = self._discover_modules(path, exclude)
            scan_phase.set_processed_count(len(modules))

        registration_count = 0
        with self._startup_phase_recorder.record_phase(
            phase_name=STARTUP_PHASE_REGISTRATION
        ) as registration_phase:
            if manifest_decision is DiscoveryManifestDecision.HIT:
                for obj in discovered_objects:
                    registration_count += self._register_discovered_object(obj)
            else:
                for item in modules:
                    objects = list_objects(
                        item,
                        lambda x: Pod.exists(x) or Tag.exists(x),
                    )
                    for obj in objects:
                        discovery_candidates.append(
                            DiscoveryManifestCandidate.from_object(obj)
                        )
                        registration_count += self._register_discovered_object(obj)
            registration_phase.set_processed_count(registration_count)

        if (
            self._discovery_manifest_path is not None
            and manifest_fingerprint is not None
            and manifest_decision is not DiscoveryManifestDecision.HIT
        ):
            manifest = DiscoveryManifest(
                fingerprint=manifest_fingerprint,
                module_names=tuple(sorted(item.__name__ for item in modules)),
                candidates=tuple(
                    sorted(
                        discovery_candidates,
                        key=lambda candidate: (
                            candidate.module_name,
                            candidate.qualname,
                        ),
                    )
                ),
            )
            DiscoveryManifestStore(self._discovery_manifest_path).save(manifest)

        return self

    def _discover_modules(self, path: Module, exclude: set[Module]) -> set[ModuleType]:
        if is_package(path):
            return list_modules(path, exclude)
        return {resolve_module(path)}

    def _register_discovered_object(self, obj: PodType) -> int:
        registration_count = 0
        if Pod.exists(obj):
            self._application_context.add(obj)
            registration_count += 1
        if Tag.exists(obj):
            tag = Tag.get(obj)
            self._application_context.register_tag(tag)
            registration_count += 1
        return registration_count

    def _resolve_manifest_hit(
        self,
        candidates: tuple[DiscoveryManifestCandidate, ...],
    ) -> "_DiscoveryManifestHit":
        discovered_objects: list[PodType] = []
        for candidate in candidates:
            matches = list_objects(
                resolve_module(candidate.module_name),
                candidate.matches,
            )
            if len(matches) != 1:
                return _DiscoveryManifestHit(
                    decision=DiscoveryManifestDecision.STALE_INPUT,
                    objects=(),
                )
            obj = next(iter(matches))
            if isinstance(obj, FunctionType) or isinstance(obj, type):
                discovered_objects.append(obj)
        return _DiscoveryManifestHit(
            decision=DiscoveryManifestDecision.HIT,
            objects=tuple(discovered_objects),
        )

    def load_plugins(
        self,
        include: set[Plugin] | None = None,
    ) -> Self:
        """Load plugins from entry points.

        Args:
            include: Optional set of plugins to load. If None, loads all available plugins.

        Returns:
            Self for method chaining.
        """
        loaded_count = 0
        with self._startup_phase_recorder.record_phase(
            phase_name=STARTUP_PHASE_LOAD_PLUGINS
        ) as plugin_phase:
            for entry_point in entry_points(
                group=PLUGIN_PATH
            ):  # pragma: no cover - coverage boundary
                if include is not None:  # pragma: no cover - coverage boundary
                    if (
                        Plugin(name=entry_point.name) not in include
                    ):  # pragma: no cover - coverage boundary
                        continue  # pragma: no cover - coverage boundary
                entry_point_function: Callable[[SpakkyApplication], None] = (
                    entry_point.load()
                )
                loaded_count += 1
                plugin_phase.set_processed_count(loaded_count)
                entry_point_function(self)  # pragma: no cover - coverage boundary
        return self

    def start(self) -> Self:
        """Start the application by initializing all Pods and running post-processors.

        Returns:
            Self for method chaining.
        """
        self._application_context.start(
            startup_phase_recorder=self._startup_phase_recorder
        )
        return self

    def stop(self) -> Self:
        """Stop the application and clean up resources.

        Returns:
            Self for method chaining.
        """
        self._application_context.stop()
        return self
