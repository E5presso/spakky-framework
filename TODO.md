# Project TODOs & Technical Debt 📝

## 🚀 Roadmap

### Core Framework
- [ ] **Responsibility Separation**: Consider splitting `ApplicationContext` into smaller components (PodRegistry, DependencyResolver, ScopeManager, ServiceManager).

### Domain Package
- [ ] **Repository**: Consider adding pagination and Specification pattern support.

### Plugins
- [ ] **RabbitMQ/Kafka Abstraction**: Extract common logic between RabbitMQ and Kafka plugins into shared base classes.

### Documentation
- [ ] Add a "Cookbook" section with common patterns (e.g., Caching, Validation).
- [ ] Document advanced AOP usage (custom pointcuts, combining aspects).
- [ ] Document thread safety guarantees explicitly.

## ✅ Completed
- [x] **Error Handling**: Improved `CircularDependencyGraphDetectedError` to show visual dependency tree with `__str__` method. Updated CONTRIBUTING.md to allow `__init__` and `__str__` overrides for context-rich errors. Added test to verify tree visualization format.
- [x] **Performance Optimization**: Optimized `__resolve_candidate` in `ApplicationContext` by adding fast path for single Pod candidates (O(1) return without filtering). Improved code clarity with explicit branching for empty/single/multiple candidate scenarios. All 43 tests pass.
- [x] **Entity Auto-Update**: Implemented auto-update for `updated_at` and `version` fields in `AbstractEntity.__setattr__()`. When a business attribute changes after initialization, metadata is automatically updated (timestamp and version UUID). Metadata fields themselves don't trigger updates. Rollback logic ensures metadata consistency on validation failure. Added comprehensive tests covering normal updates, metadata field handling, and rollback scenarios.
- [x] **Module Exports**: Added explicit re-exports in `__init__.py` files for `spakky.domain`, `spakky.event`, and `spakky.data` packages. Users can now use `from spakky.domain import AbstractEntity, AbstractValueObject` instead of deep imports.
- [x] **ValueObject Hash**: Fixed XOR-based hash to use `hash(astuple(self))` for proper order-preserving hashing. Added tests to verify order sensitivity and set operations.
- [x] **Kafka Docstring**: Fixed docstring formatting in `KafkaPostProcessor.post_process()` - removed duplicate Args section and fixed ordering.
- [x] **Concurrency Review**: Fixed race conditions in `ApplicationContext.stop()` by adding `__shutdown_lock` to serialize shutdown operations. Stored local references to `__event_loop` and `__event_thread` to prevent race conditions during cleanup. Added concurrency test to verify thread-safe shutdown.
- [x] **Thread Safety**: Fixed locking for lazy singleton creation in `ApplicationContext`. Used `RLock` to allow double-checked locking without deadlock, ensuring thread safety. Verified with concurrency tests.
- [x] **Domain Event Hash**: Fixed XOR-based hash in `AbstractDomainEvent` to use `hash((event_id, timestamp))` for proper hashing. Added tests to verify hash uniqueness and set operations.
- [x] **Security Plugin**: Added `main.py` with empty `initialize()` function and entry point registration for plugin system consistency. Security plugin provides utility functions only.
- [x] **Environment Variable Prefix Unification**: Unified RabbitMQ and Kafka environment variable prefixes to use `SPAKKY_*__` format.
- [x] **AspectPostProcessor @Pod Removal**: Removed meaningless `@Pod` decorator from `AspectPostProcessor`.
- [x] **ABC Inheritance**: All major interface classes (`IContainer`, `IEventPublisher`, `IEventConsumer`, etc.) already inherit from `ABC`.
- [x] **IEventHandlerCallback Unification**: Unified type alias definitions in `event_consumer.py` and `stereotype/event_handler.py`.
