# Persona: Architecture (아키텍처 페르소나)

> 인덱스 파일. 실제 규칙은 `.agents/rules/monorepo.md`, `.agents/rules/domain.md`, `.agents/rules/aspect.md`가 SSOT.

## 시그널

- 도메인 → 인프라 import (`from sqlalchemy`, `from pymongo` 등이 `core/spakky-domain/` 또는 `core/spakky-data/` 도메인 코드에 등장)
- 플러그인 → 다른 플러그인 직접 import (`plugins/A/src/...`에서 `from spakky_b...`)
- 1 트랜잭션 내 복수 AggregateRoot 변경
- Repository 간 직접 호출 (Repository A가 Repository B를 의존)
- Aspect가 동기 짝만 있고 비동기 짝 누락 (또는 반대)
- 레이어 단방향 위반 (`monorepo.md`의 의존 방향 매트릭스 참조)

## 심각도

전부 **Critical**. 머지 차단.

## SSOT

- `.agents/rules/monorepo.md` — 패키지별 의존 방향
- `.agents/rules/domain.md` — Aggregate 경계, Port 정의
- `.agents/rules/aspect.md` — Aspect 동기/비동기 쌍 규칙
