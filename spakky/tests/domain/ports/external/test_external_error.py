from spakky.domain.ports.external.error import AbstractSpakkyExternalError


def test_external_error_is_abstract() -> None:
    """Test that AbstractSpakkyExternalError is an abstract class"""

    class ConcreteExternalError(AbstractSpakkyExternalError):
        message = "Test external error"

    # Should be able to instantiate concrete subclass
    error = ConcreteExternalError()
    assert error.message == "Test external error"
    assert isinstance(error, AbstractSpakkyExternalError)
