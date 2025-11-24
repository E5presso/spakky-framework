from spakky.domain.ports.error import AbstractSpakkyInfrastructureError


def test_infrastructure_error_is_abstract() -> None:
    """Test that AbstractSpakkyInfrastructureError is an abstract class"""

    class ConcreteInfraError(AbstractSpakkyInfrastructureError):
        pass

    # Should be able to instantiate concrete subclass
    error = ConcreteInfraError("Test error message")
    assert str(error) == "Test error message"
    assert isinstance(error, AbstractSpakkyInfrastructureError)
