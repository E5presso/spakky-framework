import pytest

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.error import AspectInheritanceError


def test_aspect_inheritance_error_with_non_aspect_class() -> None:
    """IAspect를 상속하지 않은 클래스에 @Aspect 적용 시 AspectInheritanceError가 발생함을 검증한다."""

    with pytest.raises(AspectInheritanceError):

        @Aspect()
        class BadAspect:
            pass


def test_async_aspect_inheritance_error_with_non_aspect_class() -> None:
    """IAsyncAspect를 상속하지 않은 클래스에 @AsyncAspect 적용 시 AspectInheritanceError가 발생함을 검증한다."""

    with pytest.raises(AspectInheritanceError):

        @AsyncAspect()
        class BadAsyncAspect:
            pass


def test_aspect_inheritance_error_with_function() -> None:
    """클래스가 아닌 함수에 @Aspect 적용 시 AspectInheritanceError가 발생함을 검증한다."""

    class DummyAspect:
        pass

    with pytest.raises(AspectInheritanceError):

        @Aspect()
        def bad_aspect_function() -> DummyAspect:
            return DummyAspect()


def test_async_aspect_inheritance_error_with_function() -> None:
    """클래스가 아닌 함수에 @AsyncAspect 적용 시 AspectInheritanceError가 발생함을 검증한다."""

    class DummyAsyncAspect:
        pass

    with pytest.raises(AspectInheritanceError):

        @AsyncAspect()
        def bad_async_aspect_function() -> DummyAsyncAspect:
            return DummyAsyncAspect()
