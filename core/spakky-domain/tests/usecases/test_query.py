from spakky.domain.application.query import (
    AbstractQuery,
)


def test_abstract_query() -> None:
    """AbstractQuery의 인스턴스를 생성할 수 있음을 검증한다."""

    class TestQuery(AbstractQuery):
        pass

    query = TestQuery()
    assert isinstance(query, AbstractQuery)
