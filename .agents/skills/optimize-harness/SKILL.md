---
description: 하네스의 토큰을 최소화하면서 기능 동등성을 유지. 리뷰(중복·비추론·삭제 테스트)와 수정(포인터화·게이트 외부화·안티패턴 제거)을 한 사이클로 수행하고 `/evaluate-harness`로 회귀 검증한다.
argument-hint: "[타겟 디렉토리 또는 파일 경로]"
user-invocable: true
---

# Optimize Harness — 토큰 최적화 + 기능 동등성 보장

**규칙 추가보다 제거 우선.** 단순화 = 성능. 토큰 = 비용.

## 언제 쓰는가

- 하네스 파일에 반복·선언만·산문 설명이 누적되어 스킬 호출 시 컨텍스트가 비대해짐
- 새 규칙 추가 후 중복 확산 의심
- 주기적 점검 (월 1회 등)

## 사용법

```
/optimize-harness                              # 전체 하네스
/optimize-harness .agents/skills/example-skill/      # 특정 디렉토리
/optimize-harness path/to/file.md              # 특정 파일
```

---

## 절차

### Phase 1. 인벤토리 + 토큰 측정

- 대상 파일 목록을 `find .claude -name "*.md"`로 수집
- 파일당 word count (한국어 대략 1.5 tok/word)
- 300줄 초과 파일, 900 tokens 초과 파일을 경고 목록에 올림
- 자동 로드 파일(`AGENTS.md`) 총합이 3000 tokens를 넘는지 확인

### Phase 2. 5가지 테스트 (모든 규칙에 적용)

`harness-writing.md` "5가지 테스트" SSOT (Single Source of Truth)를 모든 규칙에 적용한다 — 1개라도 미통과면 삭제·축약 후보.

### Phase 3. 안티패턴 점검

- ❌ 디렉토리 구조 나열 → 에이전트가 직접 탐색
- ❌ 프레임워크 문서 복사 → 모델이 이미 앎
- ❌ 정중한 산문 ("...하는 것이 좋습니다") → MUST/NEVER로 교체
- ❌ 린팅/포맷팅 규칙 → hook으로 이동
- ❌ 가설적 규칙 (아직 발생 안 한 문제)
- ❌ 수사적 문장 ("X라는 단어는 함정이다")
- ❌ 번호+일반 명사 라벨 (`charter §3` 참조)
- ❌ 300줄 초과 파일

### Phase 4. 최적화 제안

각 제안에 대해:

- **대상**: 파일 경로 + 라인 범위
- **분류**: 삭제 / 병합 / 포인터화 / 외부 게이트화
- **근거**: 5가지 테스트 중 어느 것에 해당
- **예상 절감**: words / tokens

우선순위:

1. **중복 복제 해소**: 같은 규칙이 3곳 이상이면 SSOT (Single Source of Truth) 한 곳 + 나머지는 포인터
2. **선언 → 외부 게이트**: "에이전트가 스스로 점검" → `/review-code` persona·Phase self-check로 이동
3. **산문 → 명령형**: "...이 중요하다" → "...한다" 또는 삭제
4. **번호 라벨 축약**: "Device N" 같은 표현 제거 + persona 시그널 배선

### Phase 5. 사용자 승인

제안 목록을 요약해 제시. `사용자 질의` 객관식:

- 승인 — 그대로 적용
- 일부 적용 — notes로 지정
- 재논의 — Phase 4로 복귀

### Phase 6. Edit 적용

승인된 항목을 `Edit` 도구로 순차 적용. 각 편집 후 파일 상태 확인.

### Phase 7. 회귀 검증 (`/evaluate-harness` 위임)

최적화 후 **기능 동등성 필수 확인**. `Skill(evaluate-harness)`로 최근 세션 실패 시나리오 재검증:

- 포인터 체인 단절 여부
- 선언만 남고 시행 사라진 규칙 여부
- 축약으로 핵심 조항이 숨어버렸는지

조건부 통과·미통과면 Phase 4로 복귀하여 빈틈만 보강.

### Phase 8. 커밋

현재 PR 브랜치에 `/commit`. develop 직접 커밋 금지. PR이 없으면 별도 PR 생성 (`/create-pr`).

---

## 토큰 예산 (체크 기준)

- `AGENTS.md`: ≤50줄
- 자동 로드 파일 총합: ≤3000 tokens
- 파일당: ≤900 tokens
- 규칙 밀도: ≤30 tok/rule (✅) · ≤60 (⚠️) · >60 (❌)

## 파일 배치 기준

| 내용 | 위치 |
|------|------|
| 에이전트가 추론 불가능한 프로젝트 컨텍스트 | `AGENTS.md` |
| 의사결정 위계·강제 게이트 | `.agents/rules/charter.md` |
| 레이어·스타일·도메인 규약 | `.agents/rules/*.md` |
| 순서형 워크플로우 | `.agents/skills/*/` |
| 자동화 훅 | `.claude/settings.json` |

---

## 규칙

- **기능 동등성 검증 없이 종료 금지.** Phase 7은 선택이 아니라 필수.
- **"대상에 이름이 있으면 이름으로 부른다" (charter §3).** 번호+일반 명사 라벨 금지.
- **SSOT (Single Source of Truth) 중복 제거 시 포인터가 반드시 유효한지 확인.** 포인터 대상이 charter §1이면 charter §1이 그 규칙을 실제로 담고 있어야 함.
- **편집은 현재 PR 브랜치에.** 로컬에만 남기거나 develop 직접 커밋 금지.
