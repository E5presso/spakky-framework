# Project TODOs & Technical Debt 📝

## 🚀 Roadmap

### Core Framework
- [ ] **Concurrency Review**: Audit `ApplicationContext` for potential race conditions between the sync `__event_thread` and the main thread, especially during shutdown (`stop()`).
- [ ] **Performance**: Optimize `__resolve_candidate` for scenarios with many Pod candidates of the same type (currently O(N) filtering).
- [ ] **Error Handling**: Improve error messages for circular dependencies to show the exact path more clearly (visual tree?).
- [ ] **Startup Validation**: Add dependency graph analysis at `start()` time to detect circular dependencies early.
- [ ] **Responsibility Separation**: Consider splitting `ApplicationContext` into smaller components (PodRegistry, DependencyResolver, ScopeManager, ServiceManager).

### Domain Package
- [ ] **Module Exports**: Add explicit re-exports in `__init__.py` files for better API surface.
- [ ] **ValueObject Hash**: Fix XOR-based hash to use `hash(astuple(self))` for order-preserving hashing.
- [ ] **Entity updated_at**: Auto-update `updated_at` field on attribute changes.
- [ ] **Repository**: Consider adding pagination and Specification pattern support.

### Plugins
- [ ] **Security Plugin**: Add `main.py` with `initialize()` function and entry point registration to match other plugins.
- [ ] **RabbitMQ/Kafka Abstraction**: Extract common logic between RabbitMQ and Kafka plugins into shared base classes.
- [ ] **Kafka Docstring**: Fix docstring formatting issues in `post_processor.py`.

### Documentation
- [ ] Add a "Cookbook" section with common patterns (e.g., Caching, Validation).
- [ ] Document advanced AOP usage (custom pointcuts, combining aspects).
- [ ] Document thread safety guarantees explicitly.

## ✅ Completed
- [x] **Thread Safety**: Fixed locking for lazy singleton creation in `ApplicationContext`. Used `RLock` to allow double-checked locking without deadlock, ensuring thread safety. Verified with concurrency tests.
- [x] **Environment Variable Prefix Unification**: Unified RabbitMQ and Kafka environment variable prefixes to use `SPAKKY_*__` format.
- [x] **AspectPostProcessor @Pod Removal**: Removed meaningless `@Pod` decorator from `AspectPostProcessor`.
- [x] **ABC Inheritance**: All major interface classes (`IContainer`, `IEventPublisher`, `IEventConsumer`, etc.) already inherit from `ABC`.
- [x] **IEventHandlerCallback Unification**: Unified type alias definitions in `event_consumer.py` and `stereotype/event_handler.py`.
