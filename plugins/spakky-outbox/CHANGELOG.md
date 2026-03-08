# CHANGELOG

## 0.0.1

### Features

- Initial release: Transactional Outbox plugin (`spakky-outbox`)
- `AsyncOutboxEventBus` — `@Primary IAsyncEventBus` that writes integration events to the `spakky_event_outbox` table
- `OutboxRelay` — `AbstractAsyncBackgroundService` polling worker that delivers messages via `IAsyncEventTransport`
- `OutboxConfig` — environment-variable-driven configuration (`SPAKKY_OUTBOX__*`)
- `OutboxMessageTable` — dedicated SQLAlchemy infrastructure table with retry tracking
