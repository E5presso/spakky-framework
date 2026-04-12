---
applyTo: "**"
excludeAgent: "cloud-agent"
---

# Copilot Code Review Instructions

Spakky Framework는 Spring‑inspired DI/IoC Python 프레임워크(3.11+)입니다.
리뷰 코멘트는 **한국어**로 작성합니다.

> 규칙 정본은 `.claude/rules/*.md` — 이 파일은 PR 리뷰 체크포인트만 정의합니다.

---

## PR 리뷰 체크포인트

1. **레이어 의존 방향**: 역방향 의존이나 플러그인 간 직접 참조가 없는지 확인합니다.
2. **타입 안전**: `Any` 미사유 사용, `# type: ignore` 미사유 사용, `@override` 누락, `assert` 문 사용, 동적 속성 접근을 확인합니다.
3. **에러 처리**: 커스텀 에러 상속, silent fallback, `__str__` 오버라이드를 확인합니다.
4. **네이밍**: 접두사/접미사 규칙, 도메인 이벤트 명명을 확인합니다.
5. **테스트**: 함수 기반, docstring, 네이밍 패턴, Flaky 테스트 요소를 확인합니다.
6. **Aspect**: 동기/비동기 쌍 존재 여부를 확인합니다.
7. **Simplicity**: 요청 범위를 넘는 변경, 불필요한 추상화가 없는지 확인합니다.
8. **엣지 케이스**: None 체크 없는 Optional 접근, 빈 컬렉션 미처리를 확인합니다.

문제가 없으면 PR을 승인합니다.
