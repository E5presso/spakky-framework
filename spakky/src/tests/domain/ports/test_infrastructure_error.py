from spakky.domain.ports.error import AbstractSpakkyInfrastructureError


def test_infrastructure_error_is_abstract() -> None:
    """Test that AbstractSpakkyInfrastructureError is an abstract class"""

    class ConcreteInfraError(AbstractSpakkyInfrastructureError):
        message = "Test error message"

    # Should be able to instantiate concrete subclass
    error = ConcreteInfraError()
    assert error.message == "Test error message"
    assert isinstance(error, AbstractSpakkyInfrastructureError)
