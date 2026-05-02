---
name: evaluate-harness
description: 하네스가 선언한 규칙이 실제로 차단되는지 외부 서브에이전트로 독립 검증합니다. 선언-실행 단절, 회피 경로, 포인터 무효점을 적발합니다.
argument-hint: "[scope: rules|skills|all]"
user-invocable: true
---

# Evaluate Harness — 하네스 외부 검증

하네스 규칙이 **선언만 있고 실제 차단되지 않는** 단절을 외부 서브에이전트로 검증한다. 자기확증 편향을 구조적으로 차단하기 위해 `/review-harness`(3-strike 사후 진단)와 별개로, **사전적 회귀 검증** 용도다.

## 사용법

```bash
/evaluate-harness            # 전체 평가
/evaluate-harness rules      # rules/*.md만
/evaluate-harness skills     # skills/*/SKILL.md만
```

자동 트리거:
- `/optimize-harness` Phase 7 (회귀 검증)
- 하네스 PR 머지 직후 (recommended, 수동)

---

## Phase 1: 평가 대상 수집

스코프에 따라 대상 파일을 수집한다:

- `rules`: `.claude/rules/*.md` 전체 + `CLAUDE.md`
- `skills`: `.claude/skills/*/SKILL.md` 전체 + 하위 phase·script
- `all`: 위 둘 + `.claude/settings.json`

각 파일의 **차단 선언**(금지 표현, 필수 표현, 게이트 표현)을 추출하여 평가 항목 목록을 만든다.

## Phase 2: 외부 서브에이전트 검증 (병렬)

`Explore` 또는 `general-purpose` 서브에이전트를 **카테고리별 병렬 spawn**한다. 각 서브에이전트에게:

- 평가 대상 규칙 1개 또는 1개 그룹
- 코드베이스 탐색 권한
- 다음 4가지를 보고하도록 지시:

### 검증 4축

1. **선언-실행 단절**: 규칙이 차단을 선언하지만, 실제 코드/도구에서 차단되지 않는가?
   - 예: "src/에서 assert 금지" 선언인데 lint/hook이 차단하지 않음 → 단절.
2. **포인터 무효점**: 규칙이 다른 파일을 참조하는데, 그 파일이 없거나 해당 항목이 없는가?
3. **회피 경로**: 규칙을 형식만 지키고 의도를 우회하는 알려진 패턴이 코드베이스에 존재하는가?
4. **Stale 사실**: 규칙이 가정한 코드 구조·도구·버전이 현재와 다른가?

각 발견은 `severity: critical|warning|info`로 분류한다.

## Phase 3: 보고서 통합

서브에이전트 결과를 메인이 통합한다:

```markdown
## Evaluate Harness 보고서

스코프: {scope}
평가 대상: {N}개 규칙, {M}개 스킬

### Critical (즉시 조치)
- [규칙명] 단절: {설명} → 제안: {조치}

### Warning (검토 필요)
- ...

### Info (정보)
- ...

### 통과 항목: {K}개 (생략)
```

## Phase 4: 후속 분기

- **Critical 1개 이상**: 사용자에게 보고하고 `/update-harness` 또는 `/optimize-harness`로 위임 여부 질의.
- **Warning만**: 보고 후 사용자 결정 대기.
- **모두 통과**: 1줄 보고 ("Evaluate Harness: {N}개 검사 모두 통과").

---

## 규칙

- 메인 에이전트는 **검증 대상 코드를 직접 평가하지 않는다.** 외부 서브에이전트만이 평가 권한을 가진다 (자기확증 편향 차단).
- 서브에이전트는 `Explore` 또는 `general-purpose`만 사용. 코드 수정 권한 없는 에이전트로 한정.
- 평가 결과는 **차단 선언과 실제 차단의 갭**만 보고한다. 신규 규칙 제안은 별도 워크플로(`/update-harness`).
- Phase 2 병렬 spawn은 동일 메시지에서 다중 Agent 호출로 수행한다.

$ARGUMENTS
