# Persona: Naming (네이밍 페르소나)

> 인덱스. SSOT는 `.agents/harness/rules/python-code.md`.

## 시그널

- 인터페이스에 `I` 접두사 누락 (`IUserRepository`)
- Abstract 클래스에 `Abstract` 접두사 누락 (`AbstractAggregateRoot`)
- Error 클래스에 `Error` 접미사 누락
- Async 클래스에 `Async` 접두사 누락 (동기 짝과 구분 필요 시)
- 도메인 모델 외 상속 타입에 접미사 누락
- snake_case / PascalCase 일관성 위반
- 모호한 식별자 (`data`, `info`, `tmp`, `result`)

## 심각도

**Warning**. 규칙 인용이 가능할 때만 지적 (모호한 "더 좋은 이름이 있을 것" 식 지적 금지).

## SSOT

- `.agents/harness/rules/python-code.md` — 네이밍 컨벤션
