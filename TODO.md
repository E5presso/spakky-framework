# Project TODOs & Technical Debt 📝

## 🚀 Roadmap
- **Core Framework**
  - [ ] **Concurrency Review**: Audit `ApplicationContext` for potential race conditions between the sync `__event_thread` and the main thread, especially during shutdown (`stop()`).
  - [ ] **Performance**: Optimize `__resolve_candidate` for scenarios with many Pod candidates of the same type (currently O(N) filtering).
  - [ ] **Error Handling**: Improve error messages for circular dependencies to show the exact path more clearly (visual tree?).

- **Documentation**
  - [ ] Add a "Cookbook" section with common patterns (e.g., Caching, Validation).
  - [ ] Document advanced AOP usage (custom pointcuts, combining aspects).
