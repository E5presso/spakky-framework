from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent

from spakky.event.stereotype.event_handler import (
    EventHandler,
    EventRoute,
    on_event,
)


def test_event_handler() -> None:
    """@EventHandler 데코레이터가 클래스에 적용되어 있는지 확인함을 검증한다."""

    @EventHandler()
    class SampleEventHandler: ...

    class NonAnnotated: ...

    assert EventHandler.get_or_none(SampleEventHandler) is not None
    assert EventHandler.get_or_none(NonAnnotated) is None


def test_event_handler_with_callback() -> None:
    """@EventHandler와 @on_event 데코레이터가 함께 적용됨을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleEvent)
        async def handle(self, event: SampleEvent) -> None:
            print(event)

    class NonAnnotated: ...

    assert EventHandler.get_or_none(SampleEventHandler) is not None
    assert EventRoute.get_or_none(SampleEventHandler.handle) is not None
    assert EventRoute.get_or_none(SampleEventHandler().handle) is not None
    assert EventHandler.get_or_none(NonAnnotated) is None
