from spakky.domain.ports.event.error import AbstractSpakkyEventError


def test_event_error_is_abstract() -> None:
    """Test that AbstractSpakkyEventError is an abstract class"""

    class ConcreteEventError(AbstractSpakkyEventError):
        pass

    # Should be able to instantiate concrete subclass
    error = ConcreteEventError("Test event error")
    assert error.message == "Test event error"
    assert isinstance(error, AbstractSpakkyEventError)
