from spakky.data.persistency.error import AbstractSpakkyPersistencyError


def test_persistency_error_is_abstract() -> None:
    """AbstractSpakkyPersistencyError가 추상 클래스임을 검증한다."""

    class ConcretePersistencyError(AbstractSpakkyPersistencyError):
        message = "Test persistency error"

    # Should be able to instantiate concrete subclass
    error = ConcretePersistencyError()
    assert error.message == "Test persistency error"
    assert isinstance(error, AbstractSpakkyPersistencyError)
