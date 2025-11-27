from typing import Any

from pydantic import TypeAdapter
from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.event_consumer import (
    DomainEventT,
    IEventConsumer,
    IEventHandlerCallback,
)
from spakky.pod.annotations.pod import Pod
from spakky.service.background import (
    AbstractBackgroundService,
)

from spakky_kafka.common.config import KafkaConnectionConfig


@Pod()
class KafkaEventConsumer(IEventConsumer, AbstractBackgroundService):
    config: KafkaConnectionConfig
    type_lookup: dict[str, type[AbstractDomainEvent]]
    type_adapters: dict[type, TypeAdapter[AbstractDomainEvent]]
    handlers: dict[type[AbstractDomainEvent], IEventHandlerCallback[Any]]

    def __init__(self, config: KafkaConnectionConfig) -> None:
        super().__init__()
        self.config = config

    def initialize(self) -> None:
        raise NotImplementedError

    def dispose(self) -> None:
        raise NotImplementedError

    def run(self) -> None:
        raise NotImplementedError

    def register(
        self,
        event: type[DomainEventT],
        handler: IEventHandlerCallback[DomainEventT],
    ) -> None:
        raise NotImplementedError
