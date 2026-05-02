# Persona: Test & Coverage (테스트 페르소나)

> 인덱스. SSOT는 `.agents/rules/test-writing.md`.

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

## 심각도

- 변경 코드 커버리지 < 100%, 신규 분기 테스트 부재 → **Critical**
- 형식 위반, mock 남용 → **Warning**

## SSOT

- `.agents/rules/test-writing.md`
