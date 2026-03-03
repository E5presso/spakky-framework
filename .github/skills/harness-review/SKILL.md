---
name: harness-review
description: Perform a meta-review of harness compliance after completing work. Run this skill as the FINAL step of every coding session to evaluate session changes against applicable harness rules, check token budgets, and surface improvement suggestions.
---

# 하네스 메타 리뷰 워크플로우

**이 스킬은 모든 코딩 세션의 마지막 단계에서 실행합니다.**

아래 단계를 **순서대로** 수행하세요.

## Step 1: 정량 평가 실행

```bash
python .github/hooks/harness-review.py
```

생성된 `.github/hooks/harness-review.md` 리포트를 읽으세요.

## Step 2: 소스 컴플라이언스 정성 평가

리포트의 "Source Code Compliance" 섹션이 있다면, 각 변경 파일에 대해:

1. `diff`를 읽고 적용 가능한 모든 인스트럭션 규칙과 대조
2. 각 파일에 등급 부여:
   - ✅ **PASS** — 모든 적용 규칙 준수
   - ⚠️ **PARTIAL** — 일부 규칙 미준수 (개선 가능)
   - ❌ **FAIL** — 명백한 규칙 위반 존재
3. PARTIAL/FAIL 파일은 **즉시 수정** 적용

평가 범위: 네이밍, 타입 안전성, DDD/AOP/플러그인 패턴, 테스트 구조, 코딩 표준 전체.

## Step 3: 하네스 품질 정성 평가

리포트의 "Harness Quality Evaluation" 섹션이 있다면, 변경된 하네스 파일에 대해:

1. `diff`를 읽고 4가지 기준으로 평가:
   - **Clarity**: 규칙이 명확하고 실행 가능한가?
   - **Token efficiency**: 중복 없이 900토큰 예산 이내인가?
   - **Coverage completeness**: 의도한 범위를 빠짐없이 커버하는가?
   - **Structural soundness**: 파일 유형별 포맷(instructions/skill/hook/prompt)이 올바른가?
2. PARTIAL/FAIL 파일은 **즉시 개선** 적용

## Step 4: 수정 사항 커밋

수정 사항이 있으면 `report_progress` 도구로 커밋하세요.

## Step 5: 전체 등급 보고

```
## 세션 하네스 메타 리뷰 결과

| 파일 | 적용 규칙 | 등급 | 비고 |
|------|----------|------|------|
| ... | ... | ✅/⚠️/❌ | ... |

**전체 등급**: ✅ PASS / ⚠️ PARTIAL / ❌ FAIL
**조치 완료**: 수정된 항목 요약
```
