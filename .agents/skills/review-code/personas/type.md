# Persona: Type Discipline (타입 페르소나)

> 인덱스 파일. SSOT는 `.agents/rules/python-code.md`, `.agents/rules/type-discipline.md`.

## 시그널

- public 시그니처에 `dict[str, Any]`, `list[dict]`, raw `str`/`int` (의미 없는 범용 타입)
- 사유 없는 `Any`, `cast()`, `# type: ignore`
- `typing.Protocol` / `typing_extensions.Protocol` import, `Protocol` 상속, `@runtime_checkable` 구조 타이핑
- 순수 인터페이스 역할인데 `Abstract*` 접두사를 사용한 클래스 (`I*` 접두사로 정의해야 함)
- 부모 메서드 재정의에 `@override` 누락
- `getattr()`/`hasattr()`/`setattr()` 사유 없이 사용
- `Optional[T]`인데 None의 도메인 의미 미명시
- `TypedDict` 사용 (BaseModel로 대체 가능 시)
- 분기 가능한 상태가 raw `str`로 표현 (Enum/Literal 대체 가능 시)

## 심각도

대부분 **Warning**. `Protocol` 구조 타이핑과 순수 인터페이스 `Abstract*` 네이밍은 하네스 위반이므로 **Critical** 가능. `@override` 누락은 부모 시그니처 변경 시 silent 위험으로 **Critical** 가능.

## SSOT

- `.agents/rules/python-code.md` — Python 표준
- `.agents/rules/type-discipline.md` — 타입 의미 부호화
