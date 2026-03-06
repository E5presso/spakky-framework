# Spakky Framework 문서

이 디렉토리는 Spakky Framework의 개발 및 사용 가이드 문서를 포함합니다.

---

## 문서 목록

### 참조 문서

| 문서                                 | 설명                                               |
| ------------------------------------ | -------------------------------------------------- |
| [용어 사전](glossary.md)             | Spakky 고유 용어 정의 (Pod, Aspect, Stereotype 등) |
| [에러 계층 구조](error-hierarchy.md) | 에러 클래스 계층과 에러 처리 패턴                  |

### 핵심 가이드

| 문서                               | 설명                                        |
| ---------------------------------- | ------------------------------------------- |
| [DI/IoC 컨테이너](di-container.md) | 의존성 주입, Pod 스코프, 순환 참조 해결     |
| [AOP 가이드](aop-guide.md)         | Aspect, Pointcut, Advice 작성법             |
| [이벤트 시스템](event-system.md)   | DomainEvent, IntegrationEvent, EventHandler |
| [플러그인 API](plugin-api.md)      | 플러그인 개발 및 확장 포인트                |

### 아키텍처 결정

| 문서                      | 설명                          |
| ------------------------- | ----------------------------- |
| [ADR 목록](adr/README.md) | Architecture Decision Records |

---

## 관련 문서

- **[README.md](../README.md)** — 프레임워크 소개 및 Quick Start
- **[ARCHITECTURE.md](../ARCHITECTURE.md)** — 전체 아키텍처 개요
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — 기여 가이드 및 코딩 스타일

---

## 문서 우선순위

문서와 코드가 불일치할 경우:

```
Code > CONTRIBUTING.md > docs/ > README.md
```

**코드가 진실입니다.** 불일치를 발견하면 문서를 업데이트하세요.
