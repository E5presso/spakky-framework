from spakky.domain.application.query import (
    AbstractQuery,
)


def test_abstract_query() -> None:
    """Test AbstractQuery creation"""

    class TestQuery(AbstractQuery):
        pass

    query = TestQuery()
    assert isinstance(query, AbstractQuery)
