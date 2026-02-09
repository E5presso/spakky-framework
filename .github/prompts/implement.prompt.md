---
name: implement
description: Spakky Framework 기능 구현 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - edit/editFiles
  - edit/createFile
  - edit/createDirectory
  - search
  - search/listDirectory
  - execute/runTests
  - execute/testFailure
  - read/problems
  - execute/runInTerminal
  - execute/getTerminalOutput
  - search/changes
  - search/usages
  - todo
  - agent
---

# 기능 구현 워크플로우

아래 단계를 **순서대로** 수행하세요.

## Step 1: 컨텍스트 수집

1. [CONTRIBUTING.md](../../CONTRIBUTING.md)를 읽고 코딩 표준을 확인하세요.
2. 관련 기존 코드를 검색하여 패턴을 파악하세요.
3. 유사한 기능의 구현 예제를 최소 2개 찾으세요.

## Step 2: 계획 수립

1. `manage_todo_list`로 작업을 세분화하세요.
2. 각 단계는 검증 가능한 단위여야 합니다.

## Step 3: 구현

1. 기존 패턴을 따라 구현하세요.
2. 각 파일 생성/수정 후 `get_errors`로 타입 에러를 확인하세요.
3. `Any` 타입, `# type: ignore` 사용 여부를 반드시 점검하세요.

## Step 4: 테스트

1. 테스트 파일을 작성하세요 (함수 기반, `test_<function>_<scenario>_expect_<result>` 네이밍).
2. **`runTests` 도구로 실행**하세요 (터미널 사용 금지).
3. 모든 테스트가 통과할 때까지 반복하세요.

## Step 5: 검증

1. 매직 넘버가 없는지 확인하세요.
2. 에러 클래스가 프레임워크 패턴을 따르는지 확인하세요.
3. docstring이 Google Style인지 확인하세요.

구현할 기능: ${input:feature:구현할 기능을 설명하세요}
