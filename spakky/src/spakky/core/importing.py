import importlib
import inspect
import pkgutil
import sys
from fnmatch import fnmatch
from pathlib import Path
from types import FunctionType, ModuleType
from typing import Any, Callable, TypeAlias

from spakky.core.constants import PATH
from spakky.core.error import AbstractSpakkyFrameworkError

Module: TypeAlias = ModuleType | str


class CannotScanNonPackageModuleError(AbstractSpakkyFrameworkError):
    """Raised when trying to scan a non-package module.

    Args:
        AbstractSpakkyFrameworkError (_type_): Base error class.
    """

    message = "Module that you specified is not a package module."


def resolve_module(module: Module) -> ModuleType:
    """Resolve a module from its name or return the module itself.

    Args:
        module (Module): Module or module name.

    Raises:
        ImportError: If the module cannot be imported.

    Returns:
        ModuleType: The resolved module.
    """
    if isinstance(module, str):
        try:
            return importlib.import_module(module)
        except ImportError as e:
            raise ImportError(f"Failed to import module '{module}': {e}") from e
    return module


def is_package(module: Module) -> bool:
    """Check if the given module is a package.

    Args:
        module (Module): Module or module name to check if it's a package.

    Returns:
        bool: True if the module is a package, False otherwise.
    """
    module = resolve_module(module)
    return hasattr(module, PATH)


def is_subpath_of(module: Module, patterns: set[Module]) -> bool:
    """Check if a module path matches any of the given patterns.

    Supports:
    - Exact match: "package.module"
    - Wildcard patterns: "package.\*", "package.sub.\*"
    - Prefix match: "package" matches "package.submodule"

    Args:
        module: Module or module name to check.
        patterns: Set of module patterns to match against.

    Returns:
        bool: True if the module matches any pattern, False otherwise.
    """
    if isinstance(module, ModuleType):
        module = module.__name__
    for pattern in patterns:
        if isinstance(pattern, ModuleType):
            pattern = pattern.__name__
        # Exact match
        if module == pattern:
            return True
        # Wildcard pattern match (e.g., "package.*", "package.sub.*")
        if "*" in pattern or "?" in pattern:
            if fnmatch(module, pattern):
                return True
        # Prefix match for submodules (e.g., "package" matches "package.submodule")
        if module.startswith(pattern + "."):
            return True

    return False


def is_root_package(module: ModuleType) -> bool:
    """Check if a module is a root package in sys.path.

    Args:
        module: The module to check.

    Returns:
        bool: True if the module is a root package, False otherwise.
    """
    if not hasattr(module, "__path__"):
        return False
    for path in map(Path, module.__path__):
        for sys_entry in map(Path, sys.path):
            # sys.path에 직접 포함된 경로 아래면 루트
            if path == sys_entry:  # pragma: no cover
                return True
    return False


def list_modules(
    package: Module, exclude: set[Module] | None = None
) -> set[ModuleType]:
    """List all modules within a package.

    Args:
        package: Package to scan.
        exclude: Optional set of module patterns to exclude.

    Returns:
        set[ModuleType]: Set of all modules found in the package.

    Raises:
        CannotScanNonPackageModuleError: If the module is not a package.
    """
    package = resolve_module(package)
    if not is_package(package):
        raise CannotScanNonPackageModuleError(package)
    if exclude is None:
        exclude = set()
    modules: set[ModuleType] = set()
    prefix: str = package.__name__ + "." if not is_root_package(package) else ""
    for _, name, _ in pkgutil.walk_packages(package.__path__, prefix=prefix):
        if is_subpath_of(name, exclude):
            continue
        try:
            module = importlib.import_module(name)
        except ImportError:  # pragma: no cover
            continue
        modules.add(module)
    return modules


def list_classes(
    module: ModuleType, selector: Callable[[type], bool] | None = None
) -> set[type]:
    """List all classes in a module, optionally filtered by a selector.

    Args:
        module: Module to inspect.
        selector: Optional callable to filter classes.

    Returns:
        set[type]: Set of classes found in the module.
    """
    if selector is not None:
        return {
            member
            for _, member in inspect.getmembers(
                module, lambda x: inspect.isclass(x) and selector(x)
            )
        }
    return {member for _, member in inspect.getmembers(module, inspect.isclass)}


def list_functions(
    module: ModuleType, selector: Callable[[FunctionType], bool] | None = None
) -> set[FunctionType]:
    """List all functions in a module, optionally filtered by a selector.

    Args:
        module: Module to inspect.
        selector: Optional callable to filter functions.

    Returns:
        set[FunctionType]: Set of functions found in the module.
    """
    if selector is not None:
        return {
            member
            for _, member in inspect.getmembers(
                module, lambda x: inspect.isfunction(x) and selector(x)
            )
        }
    return {member for _, member in inspect.getmembers(module, inspect.isfunction)}


def list_objects(
    module: ModuleType, selector: Callable[[Any], bool] | None = None
) -> set[FunctionType]:
    """List all classes and functions in a module, optionally filtered by a selector.

    Args:
        module: Module to inspect.
        selector: Optional callable to filter classes and functions.

    Returns:
        set[FunctionType]: Set of classes and functions found in the module.
    """
    if selector is not None:
        return {
            member
            for _, member in inspect.getmembers(
                module,
                lambda x: (inspect.isclass(x) or inspect.isfunction(x)) and selector(x),
            )
        }
    return {
        member
        for _, member in inspect.getmembers(
            module, lambda x: inspect.isclass(x) or inspect.isfunction(x)
        )
    }
