from spakky.domain.ports.persistency.error import AbstractSpakkyPersistencyError


def test_persistency_error_is_abstract() -> None:
    """Test that AbstractSpakkyPersistencyError is an abstract class"""

    class ConcretePersistencyError(AbstractSpakkyPersistencyError):
        pass

    # Should be able to instantiate concrete subclass
    error = ConcretePersistencyError("Test persistency error")
    assert error.message == "Test persistency error"
    assert isinstance(error, AbstractSpakkyPersistencyError)
