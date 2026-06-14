"""Pod annotation for dependency injection container registration.

This module provides the core @Pod decorator that marks classes and functions
as managed beans in the IoC container, along with dependency resolution logic.
"""

import inspect
import ast
from dataclasses import dataclass, field
from enum import Enum, auto
from inspect import Parameter, isclass, isfunction
from types import NoneType
from typing import (
    Annotated,
    ForwardRef,
    TypeGuard,
    cast,
    get_args,
    get_origin,
)
from uuid import UUID, uuid4

from spakky.core.common.annotation import Annotation
from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.metadata import AnnotatedType
from spakky.core.common.mro import generic_mro
from spakky.core.common.types import Class, Func, is_optional, remove_none
from spakky.core.pod.diagnostics import PodDependencyResolutionDiagnostic
from spakky.core.pod.annotations.primary import Primary
from spakky.core.pod.annotations.qualifier import Qualifier
from spakky.core.pod.error import PodAnnotationFailedError, PodInstantiationFailedError
from spakky.core.utils.casing import pascal_to_snake
from spakky.core.utils.inspection import has_default_constructor, is_instance_method


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
    collection_kind: "DependencyCollectionKind | None" = None
    collection_key_type: Class | None = None


class DependencyCollectionKind(Enum):
    """Supported collection dependency injection shapes."""

    LIST = auto()
    """Inject all matching Pods as a stable list."""

    TUPLE = auto()
    """Inject all matching Pods as a stable tuple."""

    DICT = auto()
    """Inject matching Pods keyed by registered Pod name."""


type DependencyMap = dict[str, DependencyInfo]
type PodType = Func | Class


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


class UnsupportedCollectionDependencyTypeError(PodAnnotationFailedError):
    """Raised when a collection dependency annotation is unsupported."""

    message = "Unsupported collection dependency type"


class UnexpectedDependencyNameInjectedError(PodInstantiationFailedError):
    """Raised when an unexpected dependency name is injected."""

    message = "Unexpected dependency name injected into pod"


class UnexpectedDependencyTypeInjectedError(PodInstantiationFailedError):
    """Raised when an injected dependency has wrong type."""

    message = "Unexpected dependency type injected into pod"
    dependency_diagnostic: PodDependencyResolutionDiagnostic | None

    def __init__(
        self,
        *args: object,
        dependency_diagnostic: PodDependencyResolutionDiagnostic | None = None,
    ) -> None:
        """Initialize with optional dependency graph diagnostics."""
        self.dependency_diagnostic = dependency_diagnostic
        super().__init__(*args)


@dataclass(frozen=True)
class _ResolvedAnnotatedDependency:
    actual_type: object
    metadatas: tuple[object, ...]


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

    dependencies: DependencyMap = field(init=False, default_factory=dict)
    """Map of dependency names to their injection information."""

    def __annotation_globalns(self, obj: PodType) -> dict[str, object]:
        namespace = cast(Func, obj).__globals__.copy()
        namespace.setdefault("Annotated", Annotated)
        namespace.setdefault("Qualifier", Qualifier)
        return namespace

    def __resolve_parameter_annotation(
        self,
        annotation: object,
        globalns: dict[str, object],
    ) -> object:
        if not isinstance(annotation, str):
            return annotation
        try:
            return eval(annotation, globalns)
        except NameError:
            return self.__resolve_annotated_forward_annotation(annotation, globalns)
        except (SyntaxError, TypeError):
            return annotation

    def __resolve_annotated_forward_annotation(
        self,
        annotation: str,
        globalns: dict[str, object],
    ) -> object:
        expression = ast.parse(annotation, mode="eval").body
        if not self.__is_annotated_expression(expression):
            return annotation
        annotation_parts = self.__annotated_expression_parts(expression)
        if annotation_parts is None:
            return annotation
        actual_type_node, metadata_nodes = annotation_parts
        actual_type = self.__resolve_forward_actual_type(
            node=actual_type_node,
            globalns=globalns,
        )
        metadatas = self.__resolve_metadata_nodes(
            nodes=metadata_nodes,
            globalns=globalns,
        )
        if actual_type is None or metadatas is None:
            return annotation
        return _ResolvedAnnotatedDependency(
            actual_type=actual_type,
            metadatas=metadatas,
        )

    def __is_annotated_expression(
        self, expression: ast.expr
    ) -> TypeGuard[ast.Subscript]:
        if not isinstance(expression, ast.Subscript):
            return False
        value = expression.value
        if isinstance(value, ast.Name):
            return value.id == "Annotated"
        return (
            isinstance(value, ast.Attribute)
            and value.attr == "Annotated"
            and isinstance(value.value, ast.Name)
            and value.value.id == "typing"
        )

    def __annotated_expression_parts(
        self,
        expression: ast.Subscript,
    ) -> tuple[ast.expr, tuple[ast.expr, ...]] | None:
        if not isinstance(expression.slice, ast.Tuple):
            return None
        elements = tuple(expression.slice.elts)
        if len(elements) < 2:
            return None
        return elements[0], elements[1:]

    def __resolve_forward_actual_type(
        self,
        node: ast.expr,
        globalns: dict[str, object],
    ) -> object | None:
        source = ast.unparse(node)
        try:
            return eval(source, globalns)
        except NameError:
            if isinstance(node, ast.Name):
                return node.id
            return source

    def __resolve_metadata_nodes(
        self,
        nodes: tuple[ast.expr, ...],
        globalns: dict[str, object],
    ) -> tuple[object, ...] | None:
        metadatas: list[object] = []
        for node in nodes:
            source = ast.unparse(node)
            try:
                metadatas.append(eval(source, globalns))
            except NameError:
                return None
            except (SyntaxError, TypeError):
                return None
        return tuple(metadatas)

    def __normalize_dependency_annotation(
        self, annotation: object
    ) -> tuple[object, list[Qualifier], bool]:
        qualifiers: list[Qualifier] = []
        actual_type = annotation
        if isinstance(annotation, _ResolvedAnnotatedDependency):
            actual_type = annotation.actual_type
            qualifiers = [
                metadata
                for metadata in annotation.metadatas
                if isinstance(metadata, Qualifier)
            ]
        elif self.__is_annotated_dependency(annotation):
            actual_type = Qualifier.get_actual_type(annotation)
            qualifiers = Qualifier.all(annotation)
        if isinstance(actual_type, ForwardRef):
            actual_type = actual_type.__forward_arg__
        optional = is_optional(actual_type)
        if optional:
            actual_type = remove_none(actual_type)
        return actual_type, qualifiers, optional

    def __is_annotated_dependency(self, annotation: object) -> TypeGuard[AnnotatedType]:
        return get_origin(annotation) is Annotated

    def __collection_dependency_info(
        self,
        name: str,
        annotation: object,
        has_default: bool,
        is_optional_dependency: bool,
        qualifiers: list[Qualifier],
    ) -> DependencyInfo | None:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is list:
            if len(args) != 1:
                raise UnsupportedCollectionDependencyTypeError(name, annotation)
            if self.__is_builtin_collection_element(args[0]):
                return None
            element_type = self.__collection_element_type(name, annotation, args[0])
            return DependencyInfo(
                name=name,
                type_=element_type,
                has_default=has_default,
                is_optional=is_optional_dependency,
                qualifiers=qualifiers,
                collection_kind=DependencyCollectionKind.LIST,
            )
        if origin is tuple:
            if len(args) != 2 or args[1] is not Ellipsis:
                raise UnsupportedCollectionDependencyTypeError(name, annotation)
            if self.__is_builtin_collection_element(args[0]):
                return None
            element_type = self.__collection_element_type(name, annotation, args[0])
            return DependencyInfo(
                name=name,
                type_=element_type,
                has_default=has_default,
                is_optional=is_optional_dependency,
                qualifiers=qualifiers,
                collection_kind=DependencyCollectionKind.TUPLE,
            )
        if origin is dict:
            if len(args) != 2 or args[0] is not str:
                raise UnsupportedCollectionDependencyTypeError(name, annotation)
            if self.__is_builtin_collection_element(args[1]):
                return None
            element_type = self.__collection_element_type(name, annotation, args[1])
            return DependencyInfo(
                name=name,
                type_=element_type,
                has_default=has_default,
                is_optional=is_optional_dependency,
                qualifiers=qualifiers,
                collection_kind=DependencyCollectionKind.DICT,
                collection_key_type=str,
            )
        if origin in (set, frozenset) or annotation in (
            list,
            tuple,
            dict,
            set,
            frozenset,
        ):
            raise UnsupportedCollectionDependencyTypeError(name, annotation)
        return None

    def __is_builtin_collection_element(self, element_type: object) -> bool:
        return isclass(element_type) and element_type.__module__ == "builtins"

    def __collection_element_type(
        self, name: str, annotation: object, element_type: object
    ) -> Class:
        if not isclass(element_type):
            raise UnsupportedCollectionDependencyTypeError(name, annotation)
        return element_type

    def __is_dependency_type(self, annotation: object) -> TypeGuard[Class]:
        return (
            isclass(annotation)
            or isinstance(annotation, str)
            or get_origin(annotation) is not None
        )

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

        annotation_globalns = self.__annotation_globalns(obj)
        dependencies: DependencyMap = {}
        for parameter in parameters:
            if parameter.kind == Parameter.POSITIONAL_ONLY:
                raise CannotUsePositionalOnlyArgsInPodError(obj, parameter.name)
            if parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                raise CannotUseVarArgsInPodError(obj, parameter.name)
            if parameter.annotation == Parameter.empty:
                raise CannotDeterminePodTypeError(obj, parameter.name)
            annotation = self.__resolve_parameter_annotation(
                annotation=parameter.annotation,
                globalns=annotation_globalns,
            )
            type_, qualifiers, is_optional_dependency = (
                self.__normalize_dependency_annotation(annotation)
            )
            has_default = parameter.default != Parameter.empty
            collection_dependency = self.__collection_dependency_info(
                name=parameter.name,
                annotation=type_,
                has_default=has_default,
                is_optional_dependency=is_optional_dependency,
                qualifiers=qualifiers,
            )
            if collection_dependency is not None:
                dependencies[parameter.name] = collection_dependency
                continue
            if not self.__is_dependency_type(type_):
                raise CannotDeterminePodTypeError(obj, parameter.name)
            dependencies[parameter.name] = DependencyInfo(
                name=parameter.name,
                type_=type_,
                is_optional=is_optional_dependency,
                has_default=has_default,
                qualifiers=qualifiers,
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
        if type_ is None:  # pragma: no cover - coverage boundary
            raise CannotDeterminePodTypeError
        if is_optional(type_):  # pragma: no cover - coverage boundary
            raise CannotUseOptionalReturnTypeInPodError
        if not self.name:
            self.name = pascal_to_snake(obj.__name__)
        self.type_ = type_
        self.base_types = set(generic_mro(type_))
        self.target = obj
        self.dependencies = dependencies

    def __call__[T: PodType](self, obj: T) -> T:
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
        if self is value:  # pragma: no cover - coverage boundary
            return True
        if not isinstance(value, Pod):
            return False  # pragma: no cover - coverage boundary (Pod 메타데이터 비교에서 다른 타입과 비교되지 않음)
        return self.name == value.name

    @property
    def is_primary(self) -> bool:
        """Check if this Pod is marked as primary.

        Returns:
            True if the target has @Primary annotation.
        """
        return Primary.exists(self.target)

    @property
    def dependency_qualifiers(
        self,
    ) -> dict[str, list[Qualifier]]:  # pragma: no cover - coverage boundary
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
            if name not in self.dependencies:  # pragma: no cover - coverage boundary
                raise UnexpectedDependencyNameInjectedError(self.type_, name)
            dependency_info: DependencyInfo = self.dependencies[name]
            if dependency is None:
                if dependency_info.has_default:
                    # If dependency is None and has a default value,
                    # do not include it in the final dependencies
                    # so, the default value will be used
                    continue
                if (
                    not dependency_info.is_optional
                ):  # pragma: no cover - coverage boundary
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
