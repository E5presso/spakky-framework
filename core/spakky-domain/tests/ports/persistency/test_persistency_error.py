from spakky.domain.ports.persistency.error import AbstractSpakkyPersistencyError


def test_persistency_error_is_abstract() -> None:
    """Test that AbstractSpakkyPersistencyError is an abstract class"""

    class ConcretePersistencyError(AbstractSpakkyPersistencyError):
        message = "Test persistency error"

    # Should be able to instantiate concrete subclass
    error = ConcretePersistencyError()
    assert error.message == "Test persistency error"
    assert isinstance(error, AbstractSpakkyPersistencyError)
