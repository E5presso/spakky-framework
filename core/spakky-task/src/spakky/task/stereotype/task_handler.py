"""TaskHandler stereotype and task routing decorators.

This module provides @TaskHandler stereotype and @task decorator
for organizing task-queue-driven architectures.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Callable, cast

from spakky.core.common.constants import ANNOTATION_METADATA
from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.pod.annotations.pod import Pod


type TaskAuthRequirementRef = str
"""Canonical auth requirement reference carried with task metadata."""

type TaskAuthResourceRef = str
"""Canonical resource reference attached to task auth metadata."""

type TaskAuthActionRef = str
"""Canonical action reference attached to task auth metadata."""

type TaskAuthTenantRef = str
"""Canonical tenant reference attached to task auth metadata."""


_AUTH_METADATA_MODULE = "spakky.auth.metadata"
_PROTECTED_REQUIREMENT_QUALNAME = "ProtectedRequirement"
_PUBLIC_ACCESS_QUALNAME = "PublicAccess"


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskAuthRequirementMetadata:
    """Auth requirement metadata copied onto a task route."""

    kind: str
    """Provider-neutral auth requirement category."""

    ref: TaskAuthRequirementRef
    """Canonical permission, role, scope, relation, policy, or marker ref."""

    resource: TaskAuthResourceRef | None = None
    """Optional resource reference for resource-scoped checks."""

    action: TaskAuthActionRef | None = None
    """Optional action reference for policy checks."""

    tenant: TaskAuthTenantRef | None = None
    """Optional tenant reference for tenant-scoped checks."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskAuthMetadata:
    """Auth boundary metadata associated with a task route."""

    public_access: bool = False
    """Whether the task is explicitly public."""

    requirements: tuple[TaskAuthRequirementMetadata, ...] = ()
    """Ordered, duplicate-free auth requirements inherited by the task."""

    @property
    def protected(self) -> bool:
        """Return whether this task carries protected auth requirements."""
        return len(self.requirements) > 0


@dataclass
class TaskRoute(FunctionAnnotation):
    """Annotation for marking methods as dispatchable tasks.

    Associates a method as a task that can be dispatched to a task queue.
    """

    auth_metadata: TaskAuthMetadata = field(default_factory=TaskAuthMetadata)
    """Effective auth metadata for direct in-process task invocation."""


def task[**P, T](obj: Callable[P, T]) -> Callable[P, T]:
    """Decorator for marking methods as dispatchable tasks.

    All @task methods are dispatched to the task queue by the plugin aspect.

    Example:
        @TaskHandler()
        class EmailTaskHandler:
            @task
            def send_email(self, to: str, subject: str, body: str) -> None:
                ...

    Args:
        obj: The method to mark as a task.

    Returns:
        The annotated method.
    """
    route = TaskRoute()
    return cast(Callable[P, T], route(obj))


@dataclass(eq=False)
class TaskHandler(Pod):
    """Stereotype for task handler classes.

    TaskHandlers contain methods decorated with @task that
    can be dispatched to task queues asynchronously.
    """

    ...


def collect_task_auth_metadata(
    method: object,
    *,
    owner_type: type[object] | None = None,
) -> TaskAuthMetadata:
    """Collect auth decorator metadata for a task without importing spakky-auth."""
    sources = (owner_type, method) if owner_type is not None else (method,)
    public_access = any(
        _has_auth_annotation(source, _PUBLIC_ACCESS_QUALNAME)
        for source in sources
        if source is not None
    )
    requirements = _dedupe_requirements(
        requirement
        for source in sources
        if source is not None
        for requirement in _auth_requirements_from_source(source)
    )
    return TaskAuthMetadata(public_access=public_access, requirements=requirements)


def _has_auth_annotation(source: object, qualname: str) -> bool:
    return any(
        _is_auth_annotation_type(annotation_type, qualname)
        for annotation_type, _ in _metadata_items(source)
    )


def _auth_requirements_from_source(
    source: object,
) -> tuple[TaskAuthRequirementMetadata, ...]:
    requirements: list[TaskAuthRequirementMetadata] = []
    for annotation_type, annotations in _metadata_items(source):
        if not _is_auth_annotation_type(
            annotation_type,
            _PROTECTED_REQUIREMENT_QUALNAME,
        ):
            continue
        for annotation in annotations:
            requirement = _task_auth_requirement_from_annotation(annotation)
            if requirement is not None:
                requirements.append(requirement)
    return tuple(requirements)


def _task_auth_requirement_from_annotation(
    annotation: object,
) -> TaskAuthRequirementMetadata | None:
    data = _dataclass_values(annotation)
    requirement = data.get("requirement")
    requirement_data = _dataclass_values(requirement)
    if not requirement_data:
        return None
    kind = requirement_data.get("kind")
    ref = requirement_data.get("ref")
    if kind is None or not isinstance(ref, str):
        return None
    return TaskAuthRequirementMetadata(
        kind=str(kind),
        ref=ref,
        resource=_optional_str(requirement_data.get("resource")),
        action=_optional_str(requirement_data.get("action")),
        tenant=_optional_str(requirement_data.get("tenant")),
    )


def _dataclass_values(value: object) -> dict[str, object]:
    if isinstance(value, type) or not is_dataclass(value):
        return {}
    return {
        field.name: object.__getattribute__(value, field.name)
        for field in fields(value)
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _metadata_items(
    source: object,
) -> tuple[tuple[type[object], tuple[object, ...]], ...]:
    metadata = getattr(  # framework metadata lookup mirrors Annotation internals
        source,
        ANNOTATION_METADATA,
        {},
    )
    if not isinstance(metadata, dict):
        return ()
    items: list[tuple[type[object], tuple[object, ...]]] = []
    for annotation_type, annotations in metadata.items():
        if not isinstance(annotation_type, type) or not isinstance(annotations, list):
            continue
        items.append((annotation_type, tuple(annotations)))
    return tuple(items)


def _is_auth_annotation_type(annotation_type: type[object], qualname: str) -> bool:
    return (
        annotation_type.__module__ == _AUTH_METADATA_MODULE
        and annotation_type.__qualname__ == qualname
    )


def _dedupe_requirements(
    requirements: Iterable[TaskAuthRequirementMetadata],
) -> tuple[TaskAuthRequirementMetadata, ...]:
    ordered: list[TaskAuthRequirementMetadata] = []
    seen: set[TaskAuthRequirementMetadata] = set()
    for requirement in requirements:
        if requirement in seen:
            continue
        seen.add(requirement)
        ordered.append(requirement)
    return tuple(ordered)
