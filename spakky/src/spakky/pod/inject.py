"""Utility function for manual dependency injection.

This module provides the inject() function for programmatic Pod retrieval
from the container when constructor injection is not available.
"""

from typing import overload

from spakky.core.types import ObjectT
from spakky.pod.interfaces.container import IContainer


@overload
def inject(context: IContainer, type_: type[ObjectT]) -> ObjectT: ...


@overload
def inject(context: IContainer, type_: type[ObjectT], name: str) -> ObjectT: ...


def inject(
    context: IContainer,
    type_: type[ObjectT],
    name: str | None = None,
) -> object | ObjectT:
    """Manually inject a Pod from the container.

    Args:
        context: The container to retrieve from.
        type_: The type of Pod to retrieve.
        name: Optional name qualifier.

    Returns:
        The requested Pod instance.

    Example:
        service = inject(app.container, UserService)
        named_service = inject(app.container, IRepo, "postgres")
    """
    if name is not None:
        return context.get(type_=type_, name=name)
    return context.get(type_=type_)
