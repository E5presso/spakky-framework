---
name: review
description: Spakky Framework PR 리뷰 피드백 반영 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - edit/editFiles
  - search
  - search/listDirectory
  - execute/runTests
  - execute/runInTerminal
  - execute/getTerminalOutput
  - read/problems
  - search/changes
  - search/usages
  - github/*
  - todo
---

# PR 리뷰 피드백 반영 워크플로우

아래 단계를 **순서대로** 수행하세요.

## Step 1: 리뷰 댓글 수집

1. GitHub에서 PR 리뷰 댓글 전체를 읽으세요.
2. 각 댓글을 아래 기준으로 분류하세요:

| 분류 | 설명 |
|------|------|
| **필수 수정** | 버그, 타입 에러, 코딩 표준 위반 |
| **개선 제안** | 가독성, 네이밍, 구조 개선 |
| **토론** | 설계 의사결정, 트레이드오프 |
| **무시** | 범위 밖, 의도적 패턴 |

## Step 2: 수정 범위 결정

- 각 댓글에 대해 **최소 변경**으로 해결 가능한지 판단
- 범위를 벗어나는 리팩터링 제안은 별도 이슈로 분리
- 설계 의사결정 관련 댓글은 댓글로 응답 (코드 변경 불필요)

## Step 3: 수정 적용

각 필수 수정을 적용하면서:

1. **타입 에러**: `uv run pyrefly check`로 검증
2. **코딩 표준**: `uv run ruff check .`로 검증
3. **테스트**: 관련 테스트를 `execute/runTests`로 실행
4. **새 에러 없음**: 기존 에러 무시, 내 변경으로 인한 새 에러만 수정

## Step 4: 검증 체크리스트

- [ ] 모든 필수 수정 적용
- [ ] 타입 체크 통과 (`uv run pyrefly check`)
- [ ] 린트 통과 (`uv run ruff check .`)
- [ ] 관련 테스트 통과
- [ ] 새로 추가된 코드에 docstring 작성
- [ ] `Any` 타입, `# type: ignore` 사용 없음

## Step 5: 리뷰어 응답 작성

수정 완료 후 PR 댓글로 응답할 때:

- 각 수정 내용을 간결하게 설명
- 무시한 제안에 대해 이유 설명
- 별도 이슈로 분리한 항목 링크

PR 번호: ${input:pr_number:반영할 PR 번호}
