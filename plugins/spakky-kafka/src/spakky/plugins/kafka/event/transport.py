from asyncio import (
    AbstractEventLoop,
    Future,
    gather,
    get_running_loop,
    locks,
    run_coroutine_threadsafe,
    wrap_future,
)
from collections.abc import Coroutine
from contextvars import ContextVar
from logging import getLogger
from threading import Event
from typing import Any

from aiokafka import AIOKafkaProducer
from aiokafka.structs import RecordMetadata
from confluent_kafka import KafkaError, Message, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from typing import override

from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.interfaces.service import IAsyncService, IService
from spakky.event.error import EventTransportNotRunningError
from spakky.event.event_publisher import (
    IAsyncEventTransport,
    IEventTransport,
)

from spakky.plugins.kafka.common.config import KafkaConnectionConfig

logger = getLogger(__name__)

_pending_deliveries: ContextVar[list[Future[RecordMetadata]] | None] = ContextVar(
    "spakky_kafka_pending_deliveries",
    default=None,
)
"""Records the publisher in this execution context handed over, awaiting its flush.

Publishers share the transport Pod, so delivery outcomes are tracked per execution
context (asyncio task or thread) instead of per transport. A publisher's flush then
reports exactly the records it sent, and never consumes the rejection belonging to a
publisher running next to it. send() and flush() of one batch therefore belong to the
same task — which is how the event bus and the outbox relay call them.
"""


@Pod()
class KafkaEventTransport(IEventTransport, IService):
    """Synchronous Kafka event transport using confluent_kafka Producer.

    One producer is created with the transport and reused for every publish.
    send() only queues a record for the producer's own batching, so the transport
    flushes when the application stops, closing the window where a queued record
    would die with the process.
    """

    config: KafkaConnectionConfig
    admin: AdminClient
    producer: Producer

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the Kafka producer with connection config."""
        self.config = config
        self.admin = AdminClient(self.config.connection_configuration_dict)
        self.producer = Producer(
            self.config.producer_configuration_dict,
            logger=logger,
        )

    def _create_topic(self, topic: str) -> None:
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        if topic in existing_topics:
            return
        self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
            ]
        )

    def _message_delivery_report(
        self,
        error: KafkaError | None,
        message: Message,
    ) -> None:
        if (
            error is not None
        ):  # pragma: no cover - Kafka 브로커 콜백으로 커버리지 수집 불가
            logger.error(f"Message delivery failed: {error}")
        else:
            logger.info(
                f"Message delivered to {message.topic()} [{message.partition()}] at offset {message.offset()}"
            )

    @override
    def set_stop_event(self, stop_event: Event) -> None:
        """Ignore the shutdown signal: publishing is on demand, with no loop to stop."""

    @override
    def start(self) -> None:
        """Open nothing: the producer is created together with the transport."""

    @override
    def stop(self) -> None:
        """Deliver records still queued in the producer before the process exits."""
        self.producer.flush()

    @override
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Hand a pre-serialized event payload to the Kafka producer queue.

        The payload is queued for the producer's own batching and is confirmed
        only by flush(), which the caller invokes at the end of its batch.

        Args:
            event_name: Topic name (typically the event class name).
            payload: Pre-serialized JSON bytes.
            headers: Metadata headers for trace propagation.
            partition_key: Key routing the message to one partition. None lets
                Kafka assign partitions round-robin.
        """
        self._create_topic(topic=event_name)
        self.producer.produce(
            topic=event_name,
            value=payload,
            key=partition_key.encode() if partition_key is not None else None,
            headers=dict(headers),
            callback=self._message_delivery_report,
        )
        self.producer.poll(0)

    @override
    def flush(self) -> None:
        """Block until the producer has sent every queued record.

        A record the broker rejects is reported to the delivery callback, which
        logs it — confluent_kafka surfaces no error here, so a rejected record
        does not make this call fail.
        """
        self.producer.flush()


@immutable
class _LoopBoundProducer:
    """A running producer together with the event loop that owns it."""

    producer: AIOKafkaProducer
    """Producer opened at application start."""

    loop: AbstractEventLoop
    """Event loop the producer was created on and must be driven from."""


@Pod()
class AsyncKafkaEventTransport(IAsyncEventTransport, IAsyncService):
    """Asynchronous Kafka event transport using aiokafka AIOKafkaProducer.

    The producer lives as long as the application: it is opened when the
    application starts services and closed when the application stops them.
    A producer per publish would reopen the broker connection every time, defeat
    batching, and reset the idempotent producer sequence, which is bound to a
    producer instance lifetime.

    send() hands a record over without waiting for its broker acknowledgement, so
    consecutive publishes fill one batch; flush() sends the batch out and reports
    whichever record the broker rejected. A publisher only ever learns the outcome
    of the records it handed over itself, because concurrent publishers share this
    Pod and one publisher's flush must not swallow another's rejected record.

    aiokafka binds a producer to the event loop that created it, while the
    ApplicationContext runs its services on an internal event loop of its own.
    Publishers living on another loop (HTTP request handlers, tests) therefore
    have their producer calls routed back to the producer's own loop.
    """

    config: KafkaConnectionConfig
    admin: AdminClient
    _running: _LoopBoundProducer | None
    """Producer bound to its loop while the application runs, None outside it."""

    def __init__(self, config: KafkaConnectionConfig) -> None:
        """Initialize the async Kafka transport with connection config."""
        self.config = config
        self.admin = AdminClient(self.config.connection_configuration_dict)
        self._running = None

    def _create_topic(  # pragma: no cover - Kafka 브로커 콜백으로 커버리지 수집 불가
        self, topic: str
    ) -> None:
        existing_topics: set[str] = set(self.admin.list_topics().topics.keys())
        if topic in existing_topics:
            return
        self.admin.create_topics(
            [
                NewTopic(
                    topic=topic,
                    num_partitions=self.config.number_of_partitions,
                    replication_factor=self.config.replication_factor,
                )
            ]
        )

    @property
    def _running_producer(self) -> _LoopBoundProducer:
        """Return the running producer, refusing to publish into a closed one."""
        if self._running is None:
            raise EventTransportNotRunningError
        return self._running

    async def _on_producer_loop[ResultT](
        self,
        # Coroutine send and yield types are opaque asyncio internals.
        producer_call: Coroutine[Any, Any, ResultT],
        producer_loop: AbstractEventLoop,
    ) -> ResultT:
        """Await a producer call on the event loop that owns the producer."""
        if get_running_loop() is producer_loop:
            return await producer_call
        return await wrap_future(run_coroutine_threadsafe(producer_call, producer_loop))

    @staticmethod
    def _record_delivery(delivery: Future[RecordMetadata]) -> None:
        """Attribute a handed-over record to the publisher that sent it."""
        deliveries = _pending_deliveries.get()
        if deliveries is None:
            deliveries = []
            _pending_deliveries.set(deliveries)
        deliveries.append(delivery)

    @staticmethod
    def _claim_deliveries() -> list[Future[RecordMetadata]]:
        """Take the records this publisher handed over since its previous flush."""
        deliveries = _pending_deliveries.get()
        if deliveries is None:
            return []
        _pending_deliveries.set([])
        return deliveries

    async def _confirm_deliveries(
        self,
        producer: AIOKafkaProducer,
        deliveries: list[Future[RecordMetadata]],
    ) -> None:
        """Send buffered batches out and raise whatever the broker rejected.

        Only the claimed records are awaited. Records another publisher handed
        over stay with that publisher, so a rejection is reported to whoever sent
        the record rather than to whoever happened to flush first.
        """
        await producer.flush()
        outcomes = await gather(*deliveries, return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                # Every outcome is retrieved before raising, so a second rejected
                # record does not linger as an unretrieved exception.
                raise outcome

    @override
    def set_stop_event(self, stop_event: locks.Event) -> None:
        """Ignore the shutdown signal: publishing is on demand, with no loop to stop."""

    @override
    async def start_async(self) -> None:
        """Open the producer that serves every publish until the application stops."""
        producer = AIOKafkaProducer(**self.config.async_producer_configuration_dict)
        await producer.start()
        self._running = _LoopBoundProducer(producer=producer, loop=get_running_loop())

    @override
    async def stop_async(self) -> None:
        """Deliver what is still buffered, then close the producer.

        The transport stops accepting publishes before the producer closes, so a
        service still running during shutdown is told the transport stopped
        instead of being handed a delivery failure.
        """
        running = self._running_producer
        self._running = None
        await self._on_producer_loop(
            self._close_producer(running.producer, self._claim_deliveries()),
            running.loop,
        )

    async def _close_producer(
        self,
        producer: AIOKafkaProducer,
        deliveries: list[Future[RecordMetadata]],
    ) -> None:
        """Confirm outstanding records, then close the producer regardless.

        producer.stop() delivers whatever any publisher left buffered; only the
        records this context claimed can have their outcome inspected here.
        """
        try:
            await self._confirm_deliveries(producer, deliveries)
        except Exception:
            logger.exception("Failed to deliver records buffered at shutdown")
        await producer.stop()

    @override
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Hand a pre-serialized event payload to the long-lived Kafka producer.

        The record joins the producer's current batch and is confirmed only by
        flush(), which the caller invokes at the end of its batch.

        Args:
            event_name: Topic name (typically the event class name).
            payload: Pre-serialized JSON bytes.
            headers: Metadata headers for trace propagation.
            partition_key: Key routing the message to one partition. None lets
                Kafka assign partitions round-robin.

        Raises:
            EventTransportNotRunningError: When the application has not started
                the transport's producer, or has already stopped it.
        """
        self._create_topic(topic=event_name)
        running = self._running_producer
        self._record_delivery(
            await self._on_producer_loop(
                running.producer.send(
                    topic=event_name,
                    value=payload,
                    key=partition_key.encode() if partition_key is not None else None,
                    headers=[(k, v.encode()) for k, v in headers.items()],
                ),
                running.loop,
            )
        )

    @override
    async def flush(self) -> None:
        """Block until the producer sent every record this publisher handed over.

        Raises:
            EventTransportNotRunningError: When the application has not started
                the transport's producer, or has already stopped it.
            KafkaError: When the broker rejected one of this publisher's records.
        """
        running = self._running_producer
        await self._on_producer_loop(
            self._confirm_deliveries(running.producer, self._claim_deliveries()),
            running.loop,
        )
