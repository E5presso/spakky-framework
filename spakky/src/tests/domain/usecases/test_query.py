from spakky.domain.usecases.query import (
    AbstractQuery,
    IAsyncQueryUseCase,
    IQueryUseCase,
)


def test_abstract_query() -> None:
    """Test AbstractQuery creation"""

    class TestQuery(AbstractQuery):
        pass

    query = TestQuery()
    assert isinstance(query, AbstractQuery)


def test_query_usecase_protocol() -> None:
    """Test that IQueryUseCase protocol exists"""
    assert hasattr(IQueryUseCase, "execute")


def test_async_query_usecase_protocol() -> None:
    """Test that IAsyncQueryUseCase protocol exists"""
    assert hasattr(IAsyncQueryUseCase, "execute")
