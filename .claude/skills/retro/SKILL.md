---
name: retro
description: 세션 종료 시 자가 평가를 수행하고 메모리에 기록합니다. 3-strike 누적 시 하네스 튜닝을 트리거합니다.
user-invocable: true
---

# Session-Retro — 세션 자가 평가

세션 종료 전 수행하는 하네스 준수 자가 평가. 결과를 메모리 시스템에 기록하고, 동일 위반이 3회 누적되면 `/harness-update`를 트리거한다.

## 실행 절차

### 1. 세션 변경 사항 수집

```bash
git diff --name-only HEAD
git diff --cached --name-only
```

변경된 파일이 없으면 "변경 없음 — 평가 생략"으로 종료.

### 2. 자가 평가 수행

변경된 코드를 아래 카테고리별로 검사한다. 각 항목은 pass/fail로 판정.

#### 카테고리

| ID | 카테고리 | 검사 내용 |
|----|---------|----------|
| `LAYER_VIOLATION` | 레이어 의존 | 역방향 패키지 의존 |
| `ERROR_STR_OVERRIDE` | __str__ 오버라이드 | 에러 클래스에서 __str__ 오버라이드 또는 f-string 메시지 |
| `BUILTIN_RAISE` | 빌트인 예외 raise | src/ 내에서 TypeError, ValueError 등 직접 raise |
| `ANY_TYPE` | Any 사용 | Any 타입 사유 없이 사용 |
| `SILENT_FALLBACK` | Silent fallback | 빈 pass, return None |
| `MISSING_OPT_OUT_REASON` | 사유 누락 | type: ignore, pragma: no cover 등에 사유 미기재 |
| `NAMING_VIOLATION` | 네이밍 위반 | I접두사, Abstract접두사, Error접미사, Async접두사 누락 |
| `CLASS_BASED_TEST` | 클래스 기반 테스트 | class TestXxx 사용 |
| `SCOPE_CREEP` | 범위 초과 | 요청 범위를 넘는 변경 |
| `ROOT_TOOL_RUN` | 루트 실행 | 패키지 디렉토리가 아닌 루트에서 도구 실행 |

### 3. 평가 결과를 메모리에 기록

프로젝트 메모리 디렉토리에 세션 회고 파일을 작성한다.

파일 경로: `~/.claude/projects/{project-path}/memory/retro_{YYYY-MM-DD}_{세션요약_3단어}.md`

```markdown
---
name: retro_{YYYY-MM-DD}_{세션요약}
description: 세션 회고 - {세션 요약}
type: project
---

# {세션 요약 제목} — {날짜}

## 세션 요약
{이번 세션에서 수행한 작업 1-2줄 요약}

## 평가 결과

| ID | 결과 | 비고 |
|----|------|------|
| LAYER_VIOLATION | pass/fail | |
| MISSING_OVERRIDE | pass/fail | entity.py:28 — 수정 완료 |
| ... | ... | ... |

## fails
{fail 항목 리스트 — 3-strike 감지용}
- MISSING_OVERRIDE
- LEGACY_TYPING

## 교훈
{이번 세션에서 배운 점}
```

### 4. 3-strike 누적 감지

이전 retro 메모리 파일들에서 fails 섹션을 수집한다.

동일 카테고리가 **3회 이상 fail**이면:

1. 사용자에게 보고한다: "`MISSING_OVERRIDE`가 3회 누적되었습니다. 하네스 튜닝을 트리거합니다."
2. `/harness-update`를 실행하여 해당 위반을 방지하는 규칙 강화 또는 hook 추가를 제안한다.

### 5. 결과 요약 출력

```
## Session-Retro 완료

평가: 10개 카테고리 중 9개 pass, 1개 fail
기록: {파일 경로}
3-strike: 없음 (또는 MISSING_OVERRIDE 3/3 -> /harness-update 트리거)
```

## 규칙

- 변경된 파일이 없으면 평가를 생략한다.
- fail이지만 세션 중 교정되었으면 비고에 "수정 완료"로 기록한다 (카운트에는 포함).
- 3-strike 트리거 시 사용자 확인 없이 `/harness-update`를 자동 실행한다.
