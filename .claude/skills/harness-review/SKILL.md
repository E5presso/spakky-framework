---
name: harness-review
description: 코딩 세션 종료 시 하네스 준수 여부를 메타 리뷰합니다
disable-model-invocation: true
---

# 하네스 메타 리뷰 워크플로우

**이 스킬은 모든 코딩 세션의 마지막 단계에서 실행합니다.**

## Step 1: 정량 평가 실행

```bash
# 브랜치 전체 변경 리뷰 (기본값)
uv run python .claude/hooks/harness-review.py

# uncommitted 변경만 리뷰
uv run python .claude/hooks/harness-review.py --scope worktree

# 세션 시작 이후 변경만 리뷰
uv run python .claude/hooks/harness-review.py --scope session
```

생성된 `.claude/hooks/harness-review.md` 리포트를 읽으세요.

## Step 2: 소스 컴플라이언스 정성 평가

리포트의 "Source Code Compliance" 섹션이 있다면, 각 변경 파일에 대해:

1. `diff`를 읽고 적용 가능한 모든 규칙과 대조
2. 각 파일에 등급 부여:
  - ✅ **PASS** — 모든 적용 규칙 준수
  - ⚠️ **PARTIAL** — 일부 규칙 미준수
  - ❌ **FAIL** — 명백한 규칙 위반
3. PARTIAL/FAIL 파일은 **즉시 수정**

## Step 3: 하네스 품질 정성 평가

변경된 하네스 파일에 대해 4가지 기준으로 평가:
- **Clarity**: 규칙이 명확하고 실행 가능한가?
- **Token efficiency**: 중복 없이 예산 이내인가?
- **Coverage completeness**: 의도한 범위를 빠짐없이 커버하는가?
- **Structural soundness**: 파일 유형별 포맷이 올바른가?

## Step 4: 토큰 효율 평가

| 지표 | 기준 |
|------|------|
| 개별 파일 tok/rule 밀도 | ≤30 ✅, ≤60 ⚠️, >60 ❌ |
| Always-loaded 총량 | ≤3000 ✅, ≤5000 ⚠️, >5000 ❌ |

## Step 5: 전체 등급 보고

```
## 세션 하네스 메타 리뷰 결과

| 파일 | 적용 규칙 | 등급 | 비고 |
|------|----------|------|------|
| ... | ... | ✅/⚠️/❌ | ... |

**전체 등급**: ✅ PASS / ⚠️ PARTIAL / ❌ FAIL
**조치 완료**: 수정된 항목 요약
```
