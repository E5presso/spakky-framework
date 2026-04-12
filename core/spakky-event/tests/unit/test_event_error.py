from spakky.event.error import (
    AbstractSpakkyEventError,
    UnknownEventTypeError,
)


def test_event_error_is_abstract() -> None:
    """AbstractSpakkyEventError가 추상 클래스이며 구체 클래스로 확장 가능함을 검증한다."""

    class ConcreteEventError(AbstractSpakkyEventError):
        message = "Test event error"

    error = ConcreteEventError()
    assert error.message == "Test event error"
    assert isinstance(error, AbstractSpakkyEventError)


def test_unknown_event_type_error_stores_event_type_expect_attribute_accessible() -> (
    None
):
    """UnknownEventTypeError가 __init__에서 event_type을 저장하고 super를 호출함을 검증한다."""

    class SomeType: ...

    error = UnknownEventTypeError(SomeType)
    assert error.event_type is SomeType
    assert error.message == "Unknown event type"
    assert isinstance(error, AbstractSpakkyEventError)
