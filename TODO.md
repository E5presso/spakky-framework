# Project TODOs & Technical Debt 📝

## 🚀 Roadmap

- [ ] **RabbitMQ Plugin Enhancements**
  - [ ] Add support for dead-letter queues configuration via decorators.

- **Core Framework**
  - [ ] **Concurrency Review**: Audit `ApplicationContext` for potential race conditions between the sync `__event_thread` and the main thread, especially during shutdown (`stop()`).
  - [ ] **Performance**: Optimize `__resolve_candidate` for scenarios with many Pod candidates of the same type (currently O(N) filtering).
  - [ ] **Error Handling**: Improve error messages for circular dependencies to show the exact path more clearly (visual tree?).

- **Documentation**
  - [ ] Add a "Cookbook" section with common patterns (e.g., Caching, Validation).
  - [ ] Document advanced AOP usage (custom pointcuts, combining aspects).

## 🐛 Known Issues / Technical Debt

- [ ] **Test Coverage**:
  - [ ] `spakky/application/application_context.py`: Several error paths are marked `pragma: no cover`. Write tests to trigger these specific race conditions or error states.
  - [ ] Verify `DuplicateEventHandlerError` behavior in RabbitMQ plugin with comprehensive tests.

- [ ] **Type Safety**:
  - [ ] Review `cast(ObjectT, ...)` usages in `ApplicationContext`. Try to make them safer or remove if possible.

## 📦 CI/CD

- [ ] **Release Workflow**:
  - [ ] Add a "dry-run" mode to the release workflow to test deployment logic without publishing.
  - [ ] Automate changelog generation based on Conventional Commits (currently relies on `cz bump`).
