from spakky.event.error import (
    AbstractSpakkyEventError,
)


def test_event_error_is_abstract() -> None:
    """AbstractSpakkyEventError가 추상 클래스이며 구체 클래스로 확장 가능함을 검증한다."""

    class ConcreteEventError(AbstractSpakkyEventError):
        message = "Test event error"

    error = ConcreteEventError()
    assert error.message == "Test event error"
    assert isinstance(error, AbstractSpakkyEventError)
