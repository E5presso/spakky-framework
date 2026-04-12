---
name: review-code
description: 변경된 코드를 구조적으로 검토하여 버그, 아키텍처 위반, 누락된 엣지 케이스를 찾아냅니다.
user-invocable: true
---

# Self-Review — 편집증적 코드 리뷰

변경된 코드를 의심의 눈으로 검토한다. **반드시 서브에이전트에서 실행**하여 self-confirmation bias를 방지한다.

## 실행 방법

1. `git diff` (또는 `git diff --cached`)로 변경 사항을 확인한다.
2. 아래 체크리스트를 **모두** 순회하며 위반을 찾는다.
3. 발견된 이슈를 심각도별로 분류하여 보고한다.
4. 사용자 승인 후 수정한다.

## 체크리스트

### 레이어 의존 방향

- [ ] 역방향 의존이 있는가? (하위 패키지가 상위 패키지를 import)
- [ ] 플러그인이 다른 플러그인을 직접 참조하는가? (core를 거치지 않는)

### 타입 안전 (.claude/rules/python-code.md)

- [ ] `Any` 타입이 사유 없이 사용되었는가?
- [ ] opt-out 주석(`# type: ignore`, `# pyrefly: ignore`, `# pragma: no cover`)에 사유가 누락되었는가?
- [ ] 부모 메서드 재정의에 `@override` 데코레이터가 누락되었는가?
- [ ] `src/` 내에서 `assert` 문이 사용되었는가?
- [ ] `getattr()`, `hasattr()`, `setattr()`가 사유 없이 사용되었는가?

### 에러 처리 (.claude/rules/python-code.md)

- [ ] `AbstractSpakkyFrameworkError` 가족을 상속하지 않는 에러 클래스가 있는가?
- [ ] 빌트인 예외(`TypeError`, `ValueError`)를 `src/` 내에서 직접 `raise`하는가?
- [ ] silent fallback (빈 `pass`, `return None`)이 있는가?
- [ ] `__str__` 오버라이드 또는 f-string 에러 메시지가 있는가?

### 네이밍 (.claude/rules/python-code.md)

- [ ] 인터페이스에 `I` 접두사가 누락되었는가?
- [ ] Abstract 클래스에 `Abstract` 접두사가 누락되었는가?
- [ ] Error 클래스에 `Error` 접미사가 누락되었는가?
- [ ] Async 클래스에 `Async` 접두사가 누락되었는가?
- [ ] 상속 타입 접미사가 누락되었는가? (도메인 모델 제외)

### 테스트 (.claude/rules/test-writing.md)

- [ ] `class TestXxx` 패턴이 사용되었는가? (함수 기반만 허용)
- [ ] 테스트 함수에 docstring이 누락되었는가?
- [ ] 테스트 네이밍이 `test_<대상>_<시나리오>_expect_<기대결과>` 패턴을 따르지 않는가?
- [ ] Flaky 테스트 요소가 있는가? (`time.sleep`, `datetime.now()` 직접 의존, 실행 순서 의존, 외부 네트워크 호출)

### 이슈 의도 일치 (호출자가 이슈 맥락을 전달한 경우)

- [ ] 구현이 이슈의 **목표**를 달성하는가?
- [ ] **수용 기준**이 모두 충족되는가? (각 항목별 검증)
- [ ] **제약 사항**을 위반하지 않는가?
- [ ] 이슈에 명시된 **설계 의도**(배경 및 동기)와 다른 방식으로 구현한 부분이 있는가?

### Simplicity (behavioral-guidelines.md)

- [ ] 요청 범위를 넘는 변경이 포함되어 있는가?
- [ ] 단일 사용 코드에 불필요한 추상화가 있는가?
- [ ] 200줄로 작성된 것을 50줄로 줄일 수 있는가?

### 엣지 케이스

- [ ] None 체크 없이 Optional 값에 접근하는가?
- [ ] 빈 컬렉션을 고려하지 않는 로직이 있는가?

## 보고 형식

```markdown
## Self-Review 결과

### Critical (즉시 수정)
- [파일:라인] 설명

### Warning (수정 권장)
- [파일:라인] 설명

### Info (참고)
- [파일:라인] 설명
```

## 규칙

- 이슈를 발견하지 못했더라도 체크리스트를 전부 순회했음을 명시한다.
- 수정은 사용자 확인 후에만 진행한다.
- 수정 후 `/check`를 실행하여 검증한다.
