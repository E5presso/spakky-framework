"""Pod annotation for dependency injection container registration.

This module provides the core @Pod decorator that marks classes and functions
as managed beans in the IoC container, along with dependency resolution logic.
"""

import inspect
from dataclasses import dataclass, field
from enum import Enum, auto
from inspect import Parameter, isclass, isfunction
from types import NoneType
from typing import Annotated, TypeAlias, TypeGuard, TypeVar, get_origin
from uuid import UUID, uuid4

from spakky.core.annotation import Annotation
from spakky.core.interfaces.equatable import IEquatable
from spakky.core.metadata import get_metadata
from spakky.core.mro import generic_mro
from spakky.core.types import Class, Func, is_optional
from spakky.pod.annotations.primary import Primary
from spakky.pod.annotations.qualifier import Qualifier
from spakky.pod.error import PodAnnotationFailedError, PodInstantiationFailedError
from spakky.utils.casing import pascal_to_snake
from spakky.utils.inspection import has_default_constructor, is_instance_method


@dataclass
class DependencyInfo:
    """Information about a Pod's dependency for injection.

    Attributes:
        name: The parameter name of the dependency.
        type_: The type of the dependency.
        has_default: Whether the dependency has a default value.
        is_optional: Whether the dependency is optional (can be None).
        qualifiers: List of qualifiers for disambiguation.
    """

    name: str
    type_: Class
    has_default: bool = False
    is_optional: bool = False
    qualifiers: list[Qualifier] = field(default_factory=list[Qualifier])


DependencyMap: TypeAlias = dict[str, DependencyInfo]
PodType: TypeAlias = Func | Class
PodT = TypeVar("PodT", bound=PodType)


class CannotDeterminePodTypeError(PodAnnotationFailedError):
    """Raised when Pod type cannot be inferred from annotations."""

    message = "Cannot determine pod type from annotations"


class CannotUseVarArgsInPodError(PodAnnotationFailedError):
    """Raised when *args or **kwargs are used in Pod dependencies."""

    message = "Cannot use variable arguments (*args or **kwargs) in pod"


class CannotUsePositionalOnlyArgsInPodError(PodAnnotationFailedError):
    """Raised when positional-only arguments are used in Pod."""

    message = "Cannot use positional-only arguments in pod"


class CannotUseOptionalReturnTypeInPodError(PodAnnotationFailedError):
    """Raised when function Pod has Optional return type."""

    message = "Cannot use optional return type in pod"


class UnexpectedDependencyNameInjectedError(PodInstantiationFailedError):
    """Raised when an unexpected dependency name is injected."""

    message = "Unexpected dependency name injected into pod"


class UnexpectedDependencyTypeInjectedError(PodInstantiationFailedError):
    """Raised when an injected dependency has wrong type."""

    message = "Unexpected dependency type injected into pod"


@dataclass(eq=False)
class Pod(Annotation, IEquatable):
    """Annotation for marking classes and functions as managed Pods in the IoC container.

    Pods are automatically instantiated by the container with their dependencies injected.
    """

    class Scope(Enum):
        """Lifecycle scope for Pod instances."""

        SINGLETON = auto()
        """One instance shared across the entire application."""

        PROTOTYPE = auto()
        """New instance created on each request."""

        CONTEXT = auto()
        """Instance scoped to request/context lifecycle."""

    id: UUID = field(init=False, default_factory=uuid4)
    """Unique identifier for this Pod instance."""

    name: str = field(kw_only=True, default="")
    """Optional name for qualifying this Pod."""

    scope: Scope = field(kw_only=True, default=Scope.SINGLETON)
    """The lifecycle scope of this Pod."""

    type_: type = field(init=False)
    """The resolved type of this Pod."""

    base_types: set[type] = field(init=False, default_factory=set[type])
    """Set of base types and interfaces this Pod implements."""

    target: PodType = field(init=False)
    """The target class or function being registered as a Pod."""

    dependencies: DependencyMap = field(init=False, default_factory=DependencyMap)
    """Map of dependency names to their injection information."""

    def __get_dependencies(self, obj: PodType) -> DependencyMap:
        """Extract dependency information from constructor or function parameters.

        Args:
            obj: The class or function to analyze for dependencies.

        Returns:
            Map of parameter names to their dependency information.

        Raises:
            CannotUsePositionalOnlyArgsInPodError: If positional-only parameters are found.
            CannotUseVarArgsInPodError: If *args or **kwargs are found.
            CannotDeterminePodTypeError: If parameter has no type annotation.
        """
        if isclass(obj):
            if has_default_constructor(obj):
                # If obj is a class with a default constructor,
                # then return an empty dictionary
                return {}
            obj = obj.__init__  # Get constructor if obj is a class
        parameters: list[Parameter] = list(inspect.signature(obj).parameters.values())
        if is_instance_method(obj):
            # Remove self parameter if obj is an instance method
            parameters = parameters[1:]

        dependencies: DependencyMap = {}
        for parameter in parameters:
            if parameter.kind == Parameter.POSITIONAL_ONLY:
                raise CannotUsePositionalOnlyArgsInPodError(obj, parameter.name)
            if parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                raise CannotUseVarArgsInPodError(obj, parameter.name)
            if parameter.annotation == Parameter.empty:
                raise CannotDeterminePodTypeError(obj, parameter.name)
            if get_origin(parameter.annotation) is Annotated:
                type_, metadata = get_metadata(parameter.annotation)
                qualifiers = [data for data in metadata if isinstance(data, Qualifier)]
                dependencies[parameter.name] = DependencyInfo(
                    name=parameter.name,
                    type_=type_,
                    has_default=parameter.default != Parameter.empty,
                    is_optional=is_optional(parameter.annotation),
                    qualifiers=qualifiers,
                )
            else:
                dependencies[parameter.name] = DependencyInfo(
                    name=parameter.name,
                    type_=parameter.annotation,
                    is_optional=is_optional(parameter.annotation),
                    has_default=parameter.default != Parameter.empty,
                )

        return dependencies

    def _initialize(self, obj: PodType) -> None:
        """Initialize Pod metadata by analyzing the target class or function.

        Args:
            obj: The class or function to register as a Pod.

        Raises:
            CannotDeterminePodTypeError: If Pod type cannot be determined.
            CannotUseOptionalReturnTypeInPodError: If function has Optional return type.
        """
        type_: type | None = None
        dependencies: DependencyMap = self.__get_dependencies(obj)
        if isfunction(obj):
            # If obj is a function,
            # then the pod type is the return type of the function
            return_type: type = inspect.signature(obj).return_annotation
            if return_type == Parameter.empty:
                raise CannotDeterminePodTypeError(obj, return_type)
            type_ = return_type
        if isclass(obj):
            # If obj is a class, then the pod type is the class itself
            type_ = obj
        if type_ is None:  # pragma: no cover
            raise CannotDeterminePodTypeError
        if is_optional(type_):  # pragma: no cover
            raise CannotUseOptionalReturnTypeInPodError
        if not self.name:
            self.name = pascal_to_snake(obj.__name__)
        self.type_ = type_
        self.base_types = set(generic_mro(type_))
        self.target = obj
        self.dependencies = dependencies

    def __call__(self, obj: PodT) -> PodT:
        """Apply Pod annotation to target class or function.

        Args:
            obj: The class or function to decorate.

        Returns:
            The original object unchanged.
        """
        self._initialize(obj)
        return super().__call__(obj)

    def __hash__(self) -> int:
        """Compute hash based on Pod name.

        Returns:
            Hash value for this Pod.
        """
        return hash(self.name)

    def __eq__(self, value: object) -> bool:
        """Check equality based on Pod name.

        Args:
            value: The object to compare with.

        Returns:
            True if both Pods have the same name.
        """
        if self is value:  # pragma: no cover
            return True
        if not isinstance(value, Pod):  # pragma: no cover
            return False
        return self.name == value.name

    @property
    def is_primary(self) -> bool:
        """Check if this Pod is marked as primary.

        Returns:
            True if the target has @Primary annotation.
        """
        return Primary.exists(self.target)

    @property
    def dependency_qualifiers(self) -> dict[str, list[Qualifier]]:  # pragma: no cover
        """Get qualifiers for all dependencies.

        Returns:
            Map of dependency names to their qualifier annotations.
        """
        return {
            name: dependency.qualifiers
            for name, dependency in self.dependencies.items()
        }

    def is_family_with(self, type_: type) -> bool:
        """Check if this Pod is compatible with a given type.

        Args:
            type_: The type to check compatibility with.

        Returns:
            True if type matches Pod type or is in its base types.
        """
        return type_ == self.type_ or type_ in self.base_types

    def instantiate(self, dependencies: dict[str, object | None]) -> object:
        """Create an instance of this Pod with injected dependencies.

        Args:
            dependencies: Map of dependency names to their resolved instances.

        Returns:
            The instantiated Pod object.

        Raises:
            UnexpectedDependencyNameInjectedError: If unknown dependency name provided.
            UnexpectedDependencyTypeInjectedError: If required non-optional dependency is None.
        """
        final_dependencies: dict[str, object] = {}
        for name, dependency in dependencies.items():
            if name not in self.dependencies:  # pragma: no cover
                raise UnexpectedDependencyNameInjectedError(self.type_, name)
            dependency_info: DependencyInfo = self.dependencies[name]
            if dependency is None:
                if dependency_info.has_default:
                    # If dependency is None and has a default value,
                    # do not include it in the final dependencies
                    # so, the default value will be used
                    continue
                if not dependency_info.is_optional:  # pragma: no cover
                    raise UnexpectedDependencyTypeInjectedError(
                        self.type_,
                        {
                            "name": name,
                            "expected": dependency_info.type_,
                            "actual": NoneType,
                        },
                    )
            final_dependencies[name] = dependency
        return self.target(**final_dependencies)


def is_class_pod(pod: PodType) -> TypeGuard[Class]:
    """Check if a Pod target is a class.

    Args:
        pod: The Pod target to check.

    Returns:
        True if pod is a class type.
    """
    return isclass(pod)


def is_function_pod(pod: PodType) -> TypeGuard[Func]:
    """Check if a Pod target is a function.

    Args:
        pod: The Pod target to check.

    Returns:
        True if pod is a function.
    """
    return isfunction(pod)
