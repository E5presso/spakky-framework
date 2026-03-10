---
name: test
description: Spakky Framework 테스트 작성 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - edit/editFiles
  - edit/createFile
  - search
  - search/listDirectory
  - execute/runTests
  - execute/testFailure
  - read/problems
  - search/usages
  - todo
---

# 테스트 작성 워크플로우

## Step 1: 기존 패턴 확인

1. 대상 패키지의 기존 테스트 파일을 검색하세요.
2. fixture 구조(`conftest.py`)를 파악하세요.
3. 동일 패키지 내 테스트 네이밍 패턴을 확인하세요.

## Step 2: 테스트 작성

테스트 규칙은 `test-writing.instructions.md`가 자동 적용됩니다.
핵심: 함수 기반, `test_<함수>_<시나리오>_expect_<결과>` 네이밍, docstring 필수.

## Step 3: 실행

- **반드시 `execute/runTests` 도구를 사용**하세요.
- 터미널에서 `pytest`나 `uv run pytest`를 직접 실행하지 마세요.
- 테스트 파일 경로를 명시하세요.

## Step 4: 검증

1. 모든 테스트 통과 확인.
2. `Any` 타입 사용 여부 확인.
3. fixture scope 적절성 확인 (기본: `function`).

테스트 대상: ${input:target:테스트할 대상을 설명하세요}
