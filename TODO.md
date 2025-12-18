# Project TODOs & Technical Debt 📝

## 🚀 Roadmap

### Core Framework
- [ ] **Responsibility Separation**: Consider splitting `ApplicationContext` into smaller components (PodRegistry, DependencyResolver, ScopeManager, ServiceManager).

### Domain Package
- [ ] **Aggregate Root Events**: Relax `AbstractAggregateRoot` to support `AbstractDomainEvent` instead of just `AbstractIntegrationEvent`.

### Data Package
- [ ] **Repository Features**: Add pagination, sorting, and Specification pattern support to `IGenericRepository`.
- [ ] **Async Repository**: Add `IAsyncGenericRepository` interface for asynchronous data access.

### Plugins
- [ ] **RabbitMQ/Kafka Abstraction**: Extract common logic (type lookup, handler registration, serialization) between RabbitMQ and Kafka plugins into shared base classes in `core/spakky-event`.

### Eventing (Design Notes)
- [ ] **Event Routing (Domain vs Integration)**: Users control only the policy of promoting some `AbstractDomainEvent` to `AbstractIntegrationEvent`, independent of broker choice (Kafka/RabbitMQ are both first-class via plugins).
- [ ] **In-process Domain Dispatch**: Provide a default in-process `IDomainEventPublisher/Consumer` implementation (domain events are handled within the same service/BC).
- [ ] **Domain→Integration Bridge**: Provide an extensible mapper/registry (`AbstractDomainEvent` → `AbstractIntegrationEvent | None`) so domain events are not exported as-is.
- [ ] **Outbox (Plugin/Adapter)**: Core defines contracts (store/serializer/worker hooks); adapters implement DB-specific storage + leasing; worker publishes via `IIntegrationEventPublisher` resolved from installed plugin.
- [ ] **Outbox Strategy**: Default adapter uses polling + leasing; optional advanced adapter uses CDC (e.g., Debezium) where applicable.
- [ ] **Reliability**: Document at-least-once semantics, retry/backoff, dead-letter handling; consider optional Inbox interface for consumer idempotency.

### Documentation
- [ ] **Cookbook**: Add a section with common patterns (e.g., Caching, Validation, Transaction management).
- [ ] **Advanced AOP**: Document custom pointcuts and combining aspects.
- [ ] **Thread Safety**: Explicitly document thread safety guarantees for `ApplicationContext` and other core components.

## ✅ Completed
