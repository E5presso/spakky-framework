"""Aspect annotations for declaring AOP aspects as Pods.

This module provides decorators for marking classes as aspects that can intercept
method calls across the application.
"""

from dataclasses import dataclass, field
from inspect import getmembers

from spakky.aop.error import AspectInheritanceError
from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.aop.pointcut import (
    AbstractPointCut,
    After,
    AfterRaising,
    AfterReturning,
    Around,
    Before,
)
from spakky.core.types import AsyncFunc, Func
from spakky.pod.annotations.pod import Pod, PodType, is_class_pod


@dataclass(eq=False)
class Aspect(Pod):
    """Pod decorator for synchronous aspects.

    Marks a class as an aspect that can intercept synchronous method calls.
    The class must implement IAspect interface.
    """

    pointcuts: dict[type[AbstractPointCut], Func] = field(init=False)

    def matches(self, pod: object) -> bool:
        """Check if this aspect should be applied to a pod.

        Args:
            pod: The pod object to check for matching pointcuts.

        Returns:
            bool: True if any pointcut matches the pod, False otherwise.

        Raises:
            AspectInheritanceError: If target is not a class Pod or doesn't implement IAspect.
        """
        # Check if pod itself is callable and matches any pointcut
        if callable(pod):
            for annotation, target_method in self.pointcuts.items():
                if (advice := annotation.get_or_none(target_method)) is not None:
                    if advice.matches(pod):
                        return True
        # Cache getmembers() result to avoid repeated calls (O(n) operation)
        pod_methods = getmembers(pod, callable)
        for annotation, target_method in self.pointcuts.items():
            if (advice := annotation.get_or_none(target_method)) is not None:
                for _, method in pod_methods:
                    if advice.matches(method):
                        return True
        return False

    def _initialize(self, obj: PodType) -> None:
        super()._initialize(obj)
        if not is_class_pod(self.target):
            raise AspectInheritanceError
        if not issubclass(self.target, IAspect):
            raise AspectInheritanceError
        self.pointcuts: dict[type[AbstractPointCut], Func] = {
            Before: self.target.before,
            AfterReturning: self.target.after_returning,
            AfterRaising: self.target.after_raising,
            After: self.target.after,
            Around: self.target.around,
        }


@dataclass(eq=False)
class AsyncAspect(Pod):
    """Pod decorator for asynchronous aspects.

    Marks a class as an aspect that can intercept asynchronous method calls.
    The class must implement IAsyncAspect interface.
    """

    pointcuts: dict[type[AbstractPointCut], AsyncFunc] = field(init=False)

    def matches(self, pod: object) -> bool:
        """Check if this async aspect should be applied to a pod.

        Args:
            pod: The pod object to check for matching pointcuts.

        Returns:
            bool: True if any pointcut matches the pod, False otherwise.

        Raises:
            AspectInheritanceError: If target is not a class Pod or doesn't implement IAsyncAspect.
        """
        # Check if pod itself is callable and matches any pointcut
        if callable(pod):
            for annotation, target_method in self.pointcuts.items():
                if (advice := annotation.get_or_none(target_method)) is not None:
                    if advice.matches(pod):
                        return True
        # Cache getmembers() result to avoid repeated calls (O(n) operation)
        pod_methods = getmembers(pod, callable)
        for annotation, target_method in self.pointcuts.items():
            if (advice := annotation.get_or_none(target_method)) is not None:
                for _, method in pod_methods:
                    if advice.matches(method):
                        return True
        return False

    def _initialize(self, obj: PodType) -> None:
        super()._initialize(obj)
        if not is_class_pod(self.target):
            raise AspectInheritanceError
        if not issubclass(self.target, IAsyncAspect):
            raise AspectInheritanceError
        self.pointcuts: dict[type[AbstractPointCut], AsyncFunc] = {
            Before: self.target.before_async,
            AfterReturning: self.target.after_returning_async,
            AfterRaising: self.target.after_raising_async,
            After: self.target.after_async,
            Around: self.target.around_async,
        }
