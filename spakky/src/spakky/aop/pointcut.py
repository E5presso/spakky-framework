"""Pointcut annotations for defining when aspects should be applied.

This module provides decorators for specifying when aspect advice should intercept
method calls (before, after, around, etc.).
"""

from abc import ABC
from dataclasses import dataclass
from typing import Callable

from spakky.core.annotation import FunctionAnnotation
from spakky.core.types import Func


@dataclass
class AbstractPointCut(FunctionAnnotation, ABC):
    """Base class for pointcut annotations."""

    pointcut: Callable[[Func], bool]
    """Predicate function that determines if a method matches this pointcut."""

    def matches(self, method: Func) -> bool:
        """Check if a method matches this pointcut.

        Args:
            method: The method to check.

        Returns:
            bool: True if the method matches the pointcut predicate, False otherwise.
        """
        return self.pointcut(method)


@dataclass
class Before(AbstractPointCut):
    """Pointcut for advice that executes before a method call."""

    ...


@dataclass
class AfterReturning(AbstractPointCut):
    """Pointcut for advice that executes after a method returns successfully."""

    ...


@dataclass
class AfterRaising(AbstractPointCut):
    """Pointcut for advice that executes after a method raises an exception."""

    ...


@dataclass
class After(AbstractPointCut):
    """Pointcut for advice that executes after a method call (regardless of outcome)."""

    ...


@dataclass
class Around(AbstractPointCut):
    """Pointcut for advice that wraps around a method call, controlling its execution."""

    ...
