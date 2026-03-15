"""Pytest fixtures for cryptography tests."""

import pytest

from spakky.plugins.security.cryptography.rsa import AsymmetricKey


@pytest.fixture(scope="module")
def rsa_key_1024() -> AsymmetricKey:
    """Pre-generated 1024-bit RSA key for fast test execution."""
    return AsymmetricKey(size=1024)


@pytest.fixture(scope="module")
def rsa_key_2048() -> AsymmetricKey:
    """Pre-generated 2048-bit RSA key for fast test execution."""
    return AsymmetricKey(size=2048)


@pytest.fixture(params=[1024, 2048])
def rsa_key(
    request: pytest.FixtureRequest,
    rsa_key_1024: AsymmetricKey,
    rsa_key_2048: AsymmetricKey,
) -> AsymmetricKey:
    """Parametrized RSA key fixture for testing multiple key sizes."""
    if request.param == 1024:
        return rsa_key_1024
    return rsa_key_2048
