---
paths:
  - "**/*.py"
---

# 리뷰 휴리스틱 (시그널 인덱스)

`/review-code`·`/audit-codebase`가 코드 리뷰 시 탐지하는 **시그널 인덱스**다. 실제 규칙은 `python-code.md`, `type-discipline.md`, `domain.md`, `aspect.md`, `test-writing.md`, `monorepo.md`, `behavioral-guidelines.md`에 SSOT가 있다. 이 파일은 리뷰 카테고리와 시그널만 매핑한다.

## 카테고리 ↔ 심각도 ↔ SSOT

| # | 카테고리 | 심각도 | SSOT | 대표 시그널 |
|---|---------|--------|------|-----------|
| 1 | 레이어 의존 위반 | Critical | `monorepo.md`, `domain.md` | 도메인 → 인프라 import, 플러그인 ↔ 플러그인 import |
| 2 | 집계 경계 위반 | Critical | `domain.md` | 1 트랜잭션 내 복수 AggregateRoot 변경, Repository 간 직접 호출 |
| 3 | Aspect 비대칭 | Critical | `aspect.md` | 동기 Aspect만 작성하고 비동기 짝 누락 |
| 4 | 타입 규율 위반 | Warning | `type-discipline.md` | `dict[str, Any]` public 시그니처, 사유 없는 `Any`, 누락 `@override` |
| 5 | 빌트인 예외 raise | Critical | `python-code.md` | `src/`에서 `raise ValueError(...)`, `raise TypeError(...)` |
| 6 | assert 사용 (src) | Critical | `python-code.md` | `src/` 내 `assert` 문 |
| 7 | silent fallback | Critical | `python-code.md` | 빈 `except: pass`, 사유 없는 `return None` |
| 8 | YAGNI 역설 | Warning | `behavioral-guidelines.md` | 단일 사용 헬퍼, 호출자 0개 함수, "유연성" 추상화 |
| 9 | 테스트 누락 | Critical | `test-writing.md` | 신규 분기/조건에 테스트 부재, 변경 코드 커버리지 < 100% |
| 10 | 테스트 형식 | Warning | `test-writing.md` | `class TestXxx`, flaky 의존(시간/순서/네트워크) |
| 11 | Mock 남용 | Warning | `test-writing.md` | Integration 테스트에서 외부 시스템 mock |
| 12 | 네이밍 위반 | Warning | `python-code.md` | snake_case/PascalCase 위반, 모호한 식별자 |
| 13 | Defensive 과다 | Warning | `behavioral-guidelines.md` | 발생 불가 시나리오에 검증 추가, 내부 코드에 `isinstance` 체크 |
| 14 | Scope creep | Critical | `behavioral-guidelines.md` | 요청 범위 외 리팩터링·기능 추가, 버그 수정에 리팩터링 혼합 |

## 사용 원칙

- **Critical**은 머지 차단 사유. 0개 달성까지 반복 수정.
- **Warning**은 반박 가능. 정당한 사유가 있으면 유지·후속 티켓.
- 시그널 인덱스 자체는 **검증 도구**일 뿐, 권위는 SSOT 규칙에 있다. 시그널과 SSOT가 충돌하면 SSOT 우선, 인덱스 갱신.

## 운영 규칙

- 새 카테고리 추가 시 SSOT 파일을 먼저 갱신하고 인덱스 동기화.
- 카테고리 1개당 시그널은 2-4개로 제한. 너무 많으면 카테고리 분리 검토.
- 페르소나 파일(`skills/review-code/personas/*.md`)이 있다면 이 인덱스를 카테고리별로 참조.
