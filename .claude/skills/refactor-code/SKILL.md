---
name: refactor-code
description: 하네스 규칙 기반으로 코드베이스의 위반 사항을 전수 감사하고, 수정 후 검증까지 자동화합니다.
argument-hint: "[package-name | --all]"
user-invocable: true
---

# Refactor Code — 하네스 위반 전수 감사 & 수정

하네스 규칙 파일을 기준으로 코드베이스의 위반 사항을 자동 감지·수정·검증한다.

## 사용법

```
/refactor-code              # 변경된 패키지만 (git diff 기반)
/refactor-code --all        # 전체 패키지
/refactor-code spakky-event # 특정 패키지
```

---

## Phase 1: 대상 결정

### 1-1. 패키지 목록 수집

- `--all` → 모노레포 전체 패키지 (core/* + plugins/*)
- 특정 패키지명 → 해당 패키지만
- 인자 없음 → `git diff --name-only`로 변경된 파일에서 패키지 자동 감지

### 1-2. 하네스 규칙 로드

아래 규칙 파일을 모두 읽어 체크리스트를 구성한다:

| 규칙 파일 | 적용 대상 |
|-----------|----------|
| `.claude/rules/python-code.md` | `**/*.py` |
| `.claude/rules/test-writing.md` | `**/tests/**/*.py` |
| `.claude/rules/domain.md` | `**/domain/**/*.py` |
| `.claude/rules/aspect.md` | `**/aspects/**/*.py` |
| `.claude/rules/plugin.md` | `plugins/**/*.py` |
| `.claude/rules/monorepo.md` | 패키지 간 의존 방향 |

---

## Phase 2: 위반 감사 (병렬 서브에이전트)

패키지별로 **Explore 서브에이전트**를 병렬 실행하여 위반을 감사한다.

### 서브에이전트 프롬프트 구성

각 서브에이전트에게 다음을 전달한다:

1. **패키지 경로** (예: `core/spakky-event`)
2. **체크리스트** (Phase 1에서 로드한 규칙)
3. **출력 형식**:

```markdown
## [패키지명] 감사 결과

### 위반 목록
- [파일:라인] 위반 유형 — 설명 — 수정 방안

### Clean
위반 없음
```

### 감사 체크리스트

#### src/ 코드

- [ ] `@override` 데코레이터 누락 (부모 메서드 재정의)
- [ ] 빌트인 예외 직접 raise (`TypeError`, `ValueError`, `RuntimeError` 등)
- [ ] `assert` 문 사용 (테스트 외)
- [ ] `Any` 타입 사유 없이 사용
- [ ] opt-out 주석 사유 누락 (`# type: ignore`, `# pyrefly: ignore`, `# pragma: no cover`)
- [ ] `getattr()`/`hasattr()`/`setattr()` 사유 없이 사용
- [ ] `__str__` 오버라이드 (에러 클래스)
- [ ] silent fallback (`pass`, `return None`)
- [ ] 에러 클래스가 `AbstractSpakkyFrameworkError` 가족 미상속
- [ ] 네이밍 규칙 위반 (`I` 접두사, `Abstract` 접두사, `Error` 접미사)
- [ ] 레이어 역방향 의존

#### tests/ 코드

- [ ] `class TestXxx` 패턴 사용
- [ ] docstring 누락
- [ ] 네이밍 패턴 미준수 (`test_<대상>_<시나리오>_expect_<기대결과>`)
- [ ] Flaky 테스트 요소 (`time.sleep`, `datetime.now()` 직접 의존)

#### Python 호환성

- [ ] `from typing import override` (Python 3.12+ 전용) → `from typing_extensions import override`

### 서브에이전트 병렬 전략

- **4개 이하 패키지**: 패키지별 1개 서브에이전트
- **5개 이상**: 연관 패키지를 2~4개씩 묶어 서브에이전트당 배치

---

## Phase 3: 위반 수정

### 3-1. 수정 우선순위

1. **Critical** — 런타임 오류 유발 (import 호환성, 에러 클래스 상속)
2. **High** — 하네스 규칙 직접 위반 (`@override` 누락, 빌트인 예외)
3. **Medium** — 품질 규칙 위반 (opt-out 사유, 동적 접근 사유)
4. **Low** — 스타일/네이밍

### 3-2. 수정 방법

- **단순 패턴** (import 교체, 데코레이터 추가): `sed` 또는 `multi_replace_string_in_file`
- **에러 클래스 신설**: 패키지 `error.py`에 추가, 기존 패턴 준수
- **테스트 수정**: 기대값 변경, docstring 추가

### 3-3. 에러 클래스 신설 패턴

```python
# <패키지>/error.py
from abc import ABC
from spakky.core.common.error import AbstractSpakkyFrameworkError

class AbstractSpakky<Domain>Error(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky <Domain> errors."""
    ...

class <Specific>Error(AbstractSpakky<Domain>Error):
    """<설명>."""
    message = "<기본 메시지>"
```

### 3-4. typing_extensions 교체 패턴

```python
# Before
from typing import override

# After
from typing_extensions import override
```

기존에 `sys.version_info >= (3, 12)` 가드가 있는 파일은 그대로 유지한다.

---

## Phase 4: 검증 — `/check`

수정된 패키지별로 `/check` 스킬을 실행한다.

```
패키지별: format → lint → type check → test (커버리지 100%)
```

- **실패 시**: 원인 분석 후 수정, Phase 4 재실행
- **서브에이전트 병렬**: 독립 패키지는 동시 검증

---

## Phase 5: 메타 검증 — `/review-code` 루프

### 5-1. diff 기반 리뷰

1. `git diff --unified=3`로 전체 변경 사항을 수집한다.
2. diff를 ~850줄 단위로 분할한다.
3. 분할된 파트별로 **Explore 서브에이전트**를 병렬 실행하여 `/review-code` 체크리스트를 적용한다.

### 5-2. False Positive 방지

서브에이전트에게 **알려진 non-issue 목록**을 명시적으로 전달한다:

- `from typing_extensions import override` (version guard 없이) → 유효
- `Any` in `*args/**kwargs` proxy → Python 관례
- `hasattr`/`setattr`/`getattr` with logging `LogRecord` → 프레임워크 설계
- `# pragma: no cover` on exhaustive match → 사유 명시 시 유효
- `Exception.__init__` positional string args → 정상 동작
- **기존 미변경 코드** → 범위 외

### 5-3. 루프 종료 조건

- 리뷰에서 **실제 위반 0건** → 루프 종료
- 실제 위반 발견 → 수정 후 Phase 4(검증) → Phase 5(리뷰) 재실행
- **최대 5라운드**까지 반복 (무한루프 방지)

---

## Phase 6: 커밋

`/commit` 스킬을 호출한다.

- 여러 패키지 변경 시 scope 생략
- 대표 커밋 메시지 예시:

```
refactor: enforce harness rules across all packages

- Add @override decorators to interface method implementations
- Replace builtin exceptions with custom error classes
- Fix typing.override import for Python 3.11 compatibility
- Add reason comments to opt-out directives
```

---

## 주의사항

- **같은 파일을 동시에 수정하는 서브에이전트 금지** (충돌)
- **import와 사용 코드를 한 번에 추가** (ruff 미사용 제거 방지)
- **`uv run` 접두사 필수** (모든 Python 명령)
- **패키지 디렉토리 내에서 도구 실행** (루트에서 실행 금지)
