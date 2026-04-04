---
name: checkpoint
description: 긴 작업 중간에 WIP 커밋과 태그를 생성하여 롤백 포인트를 확보합니다.
argument-hint: "[설명]"
user-invocable: true
---

# Checkpoint — 작업 중간 저장점

긴 작업 도중 현재 상태를 WIP 커밋 + 태그로 저장하여, 문제 발생 시 안전하게 롤백할 수 있는 지점을 확보한다.

## 사용법

```
/checkpoint
/checkpoint "DI 컨테이너 resolve 로직 리팩터링 중간 상태"
```

인자: 체크포인트 설명 (선택, 없으면 자동 생성)

---

## 실행 절차

### 1. 현재 상태 확인

```bash
git status
git diff --stat
git diff --cached --stat
```

변경 사항이 없으면 "변경 없음 — 체크포인트 불필요"로 종료한다.

### 2. 체크포인트 메시지 결정

- 인자가 있으면 그것을 설명으로 사용한다.
- 인자가 없으면 `git diff --stat`에서 변경 파일을 분석하여 자동 생성한다.

메시지 형식:
```
wip: {설명}
```

### 3. 변경 사항 포맷팅

변경된 패키지 디렉토리에서 ruff format을 실행한다 (pre-commit hook 실패 방지):

```bash
cd <package-dir> && uv run ruff format .
```

여러 패키지가 변경되었으면 각 패키지에서 실행한다.

### 4. WIP 커밋 생성

변경된 파일만 명시적으로 스테이지하고 커밋한다:

```bash
git add <변경된 파일들>
git commit -m "wip: {설명}"
```

**주의**: `git add -A`, `git add .` 금지 — 변경한 파일만 명시적으로 스테이지한다.

### 5. 태그 생성

```bash
git tag checkpoint/{timestamp} -m "{설명}"
```

- `{timestamp}` 형식: `YYYYMMDD-HHmmss` (예: `20260404-143022`)
- 태그는 로컬에만 생성한다 (push하지 않는다).

### 6. 결과 출력

```
## Checkpoint 생성 완료

커밋: {SHORT_SHA} wip: {설명}
태그: checkpoint/{timestamp}
변경: {N}개 파일 (+{추가} -{삭제})

롤백: git reset --soft {SHORT_SHA}^
태그로 복원: git checkout checkpoint/{timestamp}
```

---

## 롤백 가이드

체크포인트로 롤백이 필요할 때:

### 최근 체크포인트로 되돌리기 (변경 보존)

```bash
git reset --soft <checkpoint-sha>^
```

변경 사항이 스테이지 상태로 복원된다.

### 특정 체크포인트 확인

```bash
git tag -l "checkpoint/*" --sort=-creatordate
```

### 체크포인트 정리

작업 완료 후 WIP 커밋들은 최종 커밋에 squash된다 (`/commit` 또는 PR squash merge 시). 태그 정리:

```bash
git tag -l "checkpoint/*" | xargs git tag -d
```

---

## 규칙

- **WIP 커밋은 push하지 않는다** — 로컬 전용.
- **태그도 push하지 않는다** — 로컬 전용.
- 체크포인트는 최종 커밋/PR에서 squash되므로 커밋 히스토리를 오염시키지 않는다.
- 변경 사항이 없으면 체크포인트를 생성하지 않는다.
- `uv run` 접두사 필수.
- `git add -A`, `git add .` 금지.

$ARGUMENTS
