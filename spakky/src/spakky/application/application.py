"""Main application class for bootstrapping the Spakky framework.

This module provides the SpakkyApplication class which serves as the entry point
for configuring and starting a Spakky application with DI/IoC and AOP support.
"""

import inspect
from importlib.metadata import entry_points
from pathlib import Path
from types import ModuleType
from typing import Callable, Self

from spakky.application.error import AbstractSpakkyApplicationError
from spakky.application.plugin import Plugin
from spakky.core.constants import PLUGIN_PATH
from spakky.core.importing import (
    Module,
    is_package,
    list_modules,
    list_objects,
    resolve_module,
)
from spakky.pod.annotations.pod import Pod, PodType
from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.container import IContainer


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

    def __init__(self, application_context: IApplicationContext) -> None:
        """Initialize the Spakky application.

        Args:
            application_context: The application context to manage Pods.
        """
        self._application_context = application_context

    def add(self, obj: PodType) -> Self:
        """Register a Pod class or function in the container.

        Args:
            obj: The class or function to register as a Pod.

        Returns:
            Self for method chaining.
        """
        self._application_context.add(obj)
        return self

    def scan(
        self,
        path: Module | None = None,
        exclude: set[Module] | None = None,
    ) -> Self:
        """Scan a module for Pod-annotated classes and functions.

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
        if path is None:  # pragma: no cover
            # Derive the caller's module dynamically so scan() works without
            # requiring every application to pass its root package explicitly.
            caller_frame = inspect.stack()[1]
            caller_module = inspect.getmodule(caller_frame[0])
            file_path = getattr(caller_module, "__file__", None)
            caller_package = (
                resolve_module(Path(file_path).parent.name) if file_path else None
            )
            if caller_package is None:
                raise CannotDetermineScanPathError
            path = caller_package

        if exclude is None:
            exclude = {caller_module} if caller_module else set()
        if is_package(path):
            modules = list_modules(path, exclude)
        else:  # pragma: no cover
            modules = {resolve_module(path)}

        for module_item in modules:
            for obj in list_objects(module_item, Pod.exists):
                self._application_context.add(obj)

        return self

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
        for entry_point in entry_points(group=PLUGIN_PATH):  # pragma: no cover
            if include is not None:  # pragma: no cover
                if Plugin(name=entry_point.name) not in include:  # pragma: no cover
                    continue  # pragma: no cover
            entry_point_function: Callable[[SpakkyApplication], None] = (
                entry_point.load()
            )  # pragma: no cover
            entry_point_function(self)  # pragma: no cover
        return self

    def start(self) -> Self:
        """Start the application by initializing all Pods and running post-processors.

        Returns:
            Self for method chaining.
        """
        self._application_context.start()
        return self

    def stop(self) -> Self:
        """Stop the application and clean up resources.

        Returns:
            Self for method chaining.
        """
        self._application_context.stop()
        return self
