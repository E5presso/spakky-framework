---
name: promote-memory
description: 로컬 auto-memory를 감사하여 3회 실패 확인을 통과한 항목만 공유 하네스(rules/skills)로 승격합니다. 메모리 사일로를 방지합니다.
argument-hint: ""
user-invocable: true
---

# Promote Memory — 메모리 → 하네스 승격

`~/.claude/projects/.../memory/` 자동 메모리는 **로컬 학습**이다. 보편 원리로 검증된 메모리는 공유 하네스(`.agents/rules/`·`.agents/skills/`)로 승격되어야 한다. 그렇지 않으면 새 세션·다른 머신·다른 사용자가 같은 학습을 반복하게 된다.

## 사용법

```bash
/promote-memory
```

세션 종료 후 또는 주기적으로 (월 1회 권장) 호출.

---

## Phase 1: 메모리 수집

`MEMORY.md` 인덱스와 `memory/*.md` 본문을 모두 읽어 다음으로 분류:

| 분류 | 정의 | 처리 |
|------|------|------|
| **feedback** | 사용자가 보낸 교정·확인 | 승격 후보 |
| **project** | 현재 작업의 일시적 사실 | 보류 (휘발) |
| **user** | 사용자 개인 프로필 | 보류 (개인 기밀) |
| **reference** | 외부 시스템 포인터 | 승격 후보 (해당 시) |

승격 후보는 feedback/reference만. project/user는 hands off.

## Phase 2: 3회 실패 확인 게이트

각 후보에 대해 **3회 이상의 발생 근거**가 있는지 검증:

- 동일 메모리 또는 유사 근거 메모리가 3건 이상 누적되었는가?
- 또는 단일 메모리가 3회 이상 갱신·재인용되었는가?

근거 부족 → 승격 거부 (보류).
근거 충족 → Phase 3.

이 게이트는 단발성 사건이 보편 원리로 부풀려지는 것을 차단한다 (`harness-writing.md` Test 5: 보편성).

## Phase 3: 5-Test 게이트 (보편 원리 검증)

승격 후보에 `harness-writing.md`의 5-Test를 적용:

1. 삭제 테스트
2. 비추론 테스트
3. 중복 테스트 (기존 rules와 중복인지)
4. 행동 변화 테스트
5. 보편성 테스트

5개 모두 통과한 항목만 Phase 4 진입.

## Phase 4: 승격 위치 결정

각 승격 항목의 적절한 위치를 결정:

| 후보 내용 | 승격 위치 |
|----------|---------|
| 코딩 표준 | `rules/python-code.md`·`rules/type-discipline.md` 등 |
| 행동 원칙 | `rules/behavioral-guidelines.md` |
| 워크플로 변경 | 해당 `skills/*/SKILL.md` |
| 외부 참조 | `AGENTS.md` 또는 해당 영역 README |

위치 결정 후 **외부 서브에이전트**(general-purpose)에게 통합 작업 위임.

## Phase 5: 사용자 승인 게이트

승격 제안을 사용자에게 보고:

```
## Promote Memory 제안

### 승격 후보 (3건)
1. feedback_X.md → rules/python-code.md §N
   근거: 3회 발생, 5-Test 모두 통과
   변경안: {요약}

2. ...

### 보류 (5건)
- feedback_Y.md: 1회 발생만 (3회 미달)
- ...

승인 → 적용 + 메모리 정리
```

`AskUserQuestion`으로 항목별 객관식 제시.

## Phase 6: 적용 & 메모리 정리

승인된 항목:
1. 메인이 직접 하네스 파일에 통합 적용 (Edit).
2. 원본 메모리는 `MEMORY.md`에서 제거 + 파일 삭제.
3. `/optimize-harness`를 자동 호출하여 추가된 항목이 중복/충돌을 일으키지 않는지 검증 (Phase 7 회귀 포함).

승인 거부 항목: 메모리 그대로 유지.

---

## 규칙

- **3회 실패 확인 게이트는 의무.** 1-2회 발생만으로 승격 금지.
- 5-Test 평가는 **외부 서브에이전트**가 수행 (자기확증 편향 차단).
- 사용자 승인 없이 메모리 삭제 금지.
- user/project 메모리는 절대 승격하지 않는다.
- 승격 후 `/optimize-harness` 자동 호출로 회귀 검증.

$ARGUMENTS
