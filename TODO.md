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

### Documentation
- [ ] **Cookbook**: Add a section with common patterns (e.g., Caching, Validation, Transaction management).
- [ ] **Advanced AOP**: Document custom pointcuts and combining aspects.
- [ ] **Thread Safety**: Explicitly document thread safety guarantees for `ApplicationContext` and other core components.

## ✅ Completed
