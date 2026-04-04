---
name: retro
description: 세션 종료 시 자가 평가를 수행하고 메모리에 기록합니다. 3-strike 누적 시 /review-harness → /update-harness 체인으로 하네스를 개선합니다.
user-invocable: true
---

# Session-Retro — 세션 자가 평가

세션 종료 전 수행하는 하네스 준수 자가 평가. **단일 rolling 파일**에 fail만 누적 기록하고, 동일 위반이 3회 누적되면 `/update-harness`를 트리거한다.

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

### 3. 기록 전략 — 단일 rolling 파일

**all-pass이면 메모리에 기록하지 않는다.** 사용자에게 결과만 출력하고 종료.

**fail이 1건 이상이면** 단일 파일 `retro_strikes.md`에 추가 기록한다.

파일 경로: `~/.claude/projects/{project-path}/memory/retro_strikes.md`

- 파일이 없으면 새로 생성한다.
- 파일이 있으면 `## 기록` 섹션에 행을 **추가(append)**한다.

```markdown
---
name: retro_strikes
description: 세션 회고 fail 누적 기록 — 3-strike 감지용
type: project
---

# Retro Strikes

## 기록

| 날짜 | 세션 | ID | 비고 |
|------|------|----|------|
| 2026-04-04 | #35 TracingMiddleware | SCOPE_CREEP | pyrefly 워크트리 수정 15개 패키지 영향 |
```

### 4. 3-strike 누적 감지

`retro_strikes.md`의 기록 테이블에서 동일 ID의 출현 횟수를 센다.

동일 카테고리가 **3회 이상 fail**이면:

1. 사용자에게 보고한다: "`{ID}`가 3회 누적되었습니다. 하네스 진단을 시작합니다."
2. `/review-harness {ID}`를 실행하여 위반의 근본 원인을 하네스에서 진단한다.
3. `/review-harness`가 진단 완료 후 자동으로 `/update-harness`를 호출하여 개선안을 적용한다.
4. 하네스 반영 완료 후 해당 ID의 행을 테이블에서 **삭제**하여 카운트를 리셋한다.

**체인**: `/retro` → `/review-harness` (진단) → `/update-harness` (개선)

### 5. 교훈 승격

세션에서 발견한 교훈이 **향후 세션에 반복 적용될 가치가 있을 때만** 별도 feedback 메모리로 저장한다. 일회성 교훈은 사용자에게 출력만 하고 메모리에 저장하지 않는다.

### 6. 결과 요약 출력

```
## Session-Retro 완료

평가: 10개 카테고리 중 {N}개 pass, {M}개 fail
기록: {all-pass이면 "기록 없음 (all-pass)", fail이면 "retro_strikes.md에 추가"}
3-strike: 없음 (또는 {ID} 3/3 → /update-harness 트리거)
```

## 규칙

- 변경된 파일이 없으면 평가를 생략한다.
- **all-pass 세션은 메모리에 기록하지 않는다** — context rot 방지.
- fail이지만 세션 중 교정되었으면 비고에 "수정 완료"로 기록한다 (카운트에는 포함).
- 3-strike 트리거 시 사용자 확인 없이 `/review-harness` → `/update-harness` 체인을 자동 실행한다.
- 3-strike 소진 후 하네스 반영 완료 시 해당 행을 삭제하여 카운트를 리셋한다.
