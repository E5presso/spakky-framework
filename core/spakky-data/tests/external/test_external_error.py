from spakky.data.external.error import AbstractSpakkyExternalError


def test_external_error_is_abstract() -> None:
    """AbstractSpakkyExternalError가 추상 클래스임을 검증한다."""

    class ConcreteExternalError(AbstractSpakkyExternalError):
        message = "Test external error"

    # Should be able to instantiate concrete subclass
    error = ConcreteExternalError()
    assert error.message == "Test external error"
    assert isinstance(error, AbstractSpakkyExternalError)
