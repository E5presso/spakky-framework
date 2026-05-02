# Persona: Type Discipline (타입 페르소나)

> 인덱스 파일. SSOT는 `.agents/harness/rules/python-code.md`, `.agents/harness/rules/type-discipline.md`.

## 시그널

- public 시그니처에 `dict[str, Any]`, `list[dict]`, raw `str`/`int` (의미 없는 범용 타입)
- 사유 없는 `Any`, `cast()`, `# type: ignore`
- 부모 메서드 재정의에 `@override` 누락
- `getattr()`/`hasattr()`/`setattr()` 사유 없이 사용
- `Optional[T]`인데 None의 도메인 의미 미명시
- `TypedDict` 사용 (BaseModel로 대체 가능 시)
- 분기 가능한 상태가 raw `str`로 표현 (Enum/Literal 대체 가능 시)

## 심각도

대부분 **Warning**. `@override` 누락은 부모 시그니처 변경 시 silent 위험으로 **Critical** 가능.

## SSOT

- `.agents/harness/rules/python-code.md` — Python 표준
- `.agents/harness/rules/type-discipline.md` — 타입 의미 부호화
