# Persona: Simplicity (단순성 페르소나)

> 인덱스 파일. SSOT는 `.agents/rules/behavioral-guidelines.md` (Simplicity First).

## 시그널

- 단일 사용 헬퍼 함수 (호출자 1개)
- 단일 사용 임시 변수 (의미 추가 없는)
- Pass-through `__init__` (부모 시그니처 그대로 위임)
- Defensive None 체크 (절대 None일 수 없는 자리)
- 호출 시 항상 default 값만 받는 매개변수 (사용처 없는 "유연성")
- 내부 객체 한 개를 그대로 노출하는 wrapper 클래스
- 1개 구체 타입에만 인스턴스화되는 Generic
- 200줄 메서드 (named phase 분해 후보)
- 50줄 이상 orchestrator (staticmethod 분해 후보)

## 심각도

**Warning**. 정당한 사유(공개 API 일관성, 향후 확장 약속 등)가 있으면 반박 가능.

## SSOT

- `.agents/rules/behavioral-guidelines.md` §2 Simplicity First
