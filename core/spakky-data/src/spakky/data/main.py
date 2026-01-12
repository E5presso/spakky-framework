from spakky.core.application.application import SpakkyApplication

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    TransactionalAspect,
)


def initialize(app: SpakkyApplication) -> None:
    app.add(AsyncTransactionalAspect)
    app.add(TransactionalAspect)
