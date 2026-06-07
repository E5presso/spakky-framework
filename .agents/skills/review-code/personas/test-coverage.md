# Persona: Test & Coverage (테스트 페르소나)

> 인덱스. SSOT는 `.agents/rules/test-writing.md`, API/Infra 항목은 `.agents/rules/plugin.md`, `.agents/rules/dependencies.md`, `.agents/rules/documentation.md`도 함께 적용.

## 시그널

- 신규 분기·조건에 대응하는 테스트 부재
- 변경 코드의 라인/브랜치 커버리지 < 100%
- `class TestXxx` 사용 (함수 기반만 허용)
- 시간 의존 (`sleep`, `datetime.now()` 직접 사용) — flaky
- 순서 의존 (테스트 간 fixture 공유)
- 네트워크 의존 (real HTTP 호출)
- Mock 남용 (Integration 테스트에서 외부 시스템 mock)
- 자명한 비교 한 줄 테스트 (커버리지 게이징)
- assert 없는 테스트 (실행만 하고 확인 없음)
- API/REST: 공개 endpoint·status code·DTO·환경변수 변경이 README/docs/API 문서와 불일치
- API/REST: FastAPI/Typer 등 adapter가 domain/core 타입을 외부 DTO로 그대로 노출
- Infra: plugin `initialize` 부작용·동기 I/O·외부 SDK lifecycle 누락
- Infra: 새 외부 의존/환경변수/entry-point가 pyproject·docs·설정 예시에 반영되지 않음

## 심각도

- 변경 코드 커버리지 < 100%, 신규 분기 테스트 부재 → **Critical**
- 형식 위반, mock 남용 → **Warning**

## SSOT

- `.agents/rules/test-writing.md`
- `.agents/rules/plugin.md`
- `.agents/rules/dependencies.md`
- `.agents/rules/documentation.md`
