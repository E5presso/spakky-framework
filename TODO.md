# Project TODOs & Technical Notes 📝

## 🚀 Roadmap

### Documentation
- [ ] **Cookbook**: 공통 패턴 예제 추가 (Caching, Validation, Transaction 관리)
- [ ] **Advanced AOP**: 커스텀 pointcut 및 aspect 조합 문서화
- [ ] **Thread Safety**: `ApplicationContext` 및 코어 컴포넌트의 스레드 안전성 명시

## 📋 설계 노트

> 현재 구현에서 고려 중이지만 확정되지 않은 설계 방향입니다.

### Event Reliability
- **At-least-once 시맨틱**: 재시도/백오프, dead-letter 핸들링 문서화 필요
- **Consumer Idempotency**: 선택적 Inbox 인터페이스 검토

## ✅ Completed

### Domain Package
- [x] `AbstractAggregateRoot`가 `AbstractDomainEvent` 지원

### Data Package
- [x] `IAsyncGenericRepository` 인터페이스 제공
- [x] SQLAlchemy Repository에서 `AggregateCollector.collect()` 호출

### Event Package
- [x] `DomainEventPublisher` / `AsyncDomainEventPublisher` — 인프로세스 도메인 이벤트 발행
- [x] `TransactionalEventPublishingAspect` — 트랜잭션 성공 후 이벤트 자동 발행
