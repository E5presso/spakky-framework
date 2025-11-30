import pytest

from spakky.aop.aspect import Aspect, AsyncAspect
from spakky.aop.error import AspectInheritanceError


def test_aspect_inheritance_error_with_non_aspect_class() -> None:
    """Test that Aspect raises error when class doesn't inherit from IAspect"""

    with pytest.raises(AspectInheritanceError):

        @Aspect()
        class BadAspect:
            pass


def test_async_aspect_inheritance_error_with_non_aspect_class() -> None:
    """Test that AsyncAspect raises error when class doesn't inherit from IAsyncAspect"""

    with pytest.raises(AspectInheritanceError):

        @AsyncAspect()
        class BadAsyncAspect:
            pass


def test_aspect_inheritance_error_with_function() -> None:
    """Test that Aspect raises error when target is not a class"""

    class DummyAspect:
        pass

    with pytest.raises(AspectInheritanceError):

        @Aspect()
        def bad_aspect_function() -> DummyAspect:
            return DummyAspect()


def test_async_aspect_inheritance_error_with_function() -> None:
    """Test that AsyncAspect raises error when target is not a class"""

    class DummyAsyncAspect:
        pass

    with pytest.raises(AspectInheritanceError):

        @AsyncAspect()
        def bad_async_aspect_function() -> DummyAsyncAspect:
            return DummyAsyncAspect()
