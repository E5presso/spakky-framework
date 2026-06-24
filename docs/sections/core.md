# 핵심 (Core)

> 의존성 주입, AOP, 도메인 모델, 이벤트, 태스크 — Spakky 애플리케이션의 기본 문법입니다. 어떤 경계(HTTP·CLI·메시징·Agent)를 붙이든 이 다섯 개념 위에서 출발합니다.

처음이라면 **기초**를 위에서부터 차례로 읽으세요. 이미 기본기를 익혔다면 **심화**에서 스코프·순환 참조·이벤트 시스템 내부 설계로 넘어가면 됩니다.

## 기초

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [DI & Pod](../guides/dependency-injection.md) | `@Pod()`로 컴포넌트를 등록하고 생성자 타입 힌트로 주입받기 |
| [AOP](../guides/aop.md) | 로깅·트랜잭션 같은 공통 관심사를 Aspect로 분리하기 |
| [도메인 모델링](../guides/domain-modeling.md) | Aggregate·Entity·Value Object로 도메인 모델 만들기 |
| [이벤트 시스템](../guides/events.md) | UseCase 성공 뒤 이벤트를 발행하고 처리하기 |
| [태스크 & 스케줄링](../guides/tasks.md) | 백그라운드 태스크와 주기 실행 선언하기 |

## 심화

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [DI/IoC 컨테이너](../di-container.md) | 컨테이너 내부, Pod 스코프, 순환 참조 해결 |
| [DI & Pod 심화](../guides/dependency-injection-advanced.md) | 다중 구현 해소, 조건부 등록, 한정자 |
| [AOP 가이드](../aop-guide.md) | Aspect·Pointcut·Advice 작성 상세 |
| [이벤트 시스템(심화)](../event-system.md) | DomainEvent·IntegrationEvent·EventHandler 설계 |
