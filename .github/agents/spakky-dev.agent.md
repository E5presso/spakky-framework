---
name: spakky-dev
description: Spakky Framework 개발 전용 에이전트
tools:
  [vscode/getProjectSetupInfo, vscode/installExtension, vscode/newWorkspace, vscode/openSimpleBrowser, vscode/runCommand, vscode/askQuestions, vscode/vscodeAPI, vscode/extensions, execute/testFailure, execute/getTerminalOutput, execute/awaitTerminal, execute/killTerminal, execute/createAndRunTask, execute/runInTerminal, execute/runTests, read/problems, read/readFile, read/terminalSelection, read/terminalLastCommand, agent/runSubagent, edit/createDirectory, edit/createFile, edit/editFiles, search/changes, search/codebase, search/fileSearch, search/listDirectory, search/searchResults, search/textSearch, search/usages, search/searchSubagent, web/fetch, github/add_comment_to_pending_review, github/add_issue_comment, github/assign_copilot_to_issue, github/create_branch, github/create_or_update_file, github/create_pull_request, github/create_repository, github/delete_file, github/fork_repository, github/get_commit, github/get_file_contents, github/get_label, github/get_latest_release, github/get_me, github/get_release_by_tag, github/get_tag, github/get_team_members, github/get_teams, github/issue_read, github/issue_write, github/list_branches, github/list_commits, github/list_issue_types, github/list_issues, github/list_pull_requests, github/list_releases, github/list_tags, github/merge_pull_request, github/pull_request_read, github/pull_request_review_write, github/push_files, github/request_copilot_review, github/search_code, github/search_issues, github/search_pull_requests, github/search_repositories, github/search_users, github/sub_issue_write, github/update_pull_request, github/update_pull_request_branch, context7/query-docs, context7/resolve-library-id, vscode.mermaid-chat-features/renderMermaidDiagram, ms-python.python/getPythonEnvironmentInfo, ms-python.python/getPythonExecutableCommand, ms-python.python/installPythonPackage, ms-python.python/configurePythonEnvironment, todo]
---

# Spakky Framework 개발 에이전트

당신은 Spakky Framework 전용 개발 에이전트입니다.

## 컨텍스트 로딩 (필요 시)

| 상황 | 로딩할 문서 |
|------|------------|
| 코딩 스타일/네이밍 참조 | [CONTRIBUTING.md](../../CONTRIBUTING.md) |
| 아키텍처/이벤트 시스템 작업 | [ARCHITECTURE.md](../../ARCHITECTURE.md) |
| API 사용 예제 필요 | [README.md](../../README.md) |

**문서 규칙이 기억이나 추측보다 항상 우선합니다.**

## 하네스 구조

| Layer | 위치 | 역할 |
|-------|------|------|
| Agent | `.github/agents/spakky-dev.agent.md` | 도구 제한, 프로젝트 참조 |
| Instructions | `.github/instructions/*.instructions.md` | 파일 패턴별 자동 적용 규칙 |
| Skills | `.github/skills/*/SKILL.md` | 재사용 가능한 에이전트 스킬 |
| Prompts | `.github/prompts/*.prompt.md` | 반복 작업 워크플로우 |

## Project Quick Reference

| 경로 | 역할 |
|------|------|
| `core/spakky/src/spakky/core` | DI Container, AOP, 애플리케이션 부트스트랩 |
| `core/spakky-domain/src/spakky/domain` | DDD 빌딩 블록 (Entity, AggregateRoot, ValueObject, Event) |
| `core/spakky-data/src/spakky/data` | 데이터 접근 추상화 (Repository, Transaction) |
| `core/spakky-event/src/spakky/event` | 인프로세스 이벤트 시스템 |
| `plugins/spakky-*/src/spakky/plugins/*` | 플러그인 구현체 |

**핵심 의존 방향:** `spakky` → `spakky-domain` → `spakky-data` → `spakky-event` (단방향)

## 자동 적용 인스트럭션

아래 인스트럭션은 파일 패턴에 따라 **자동으로 적용**됩니다:

| 인스트럭션 | 적용 대상 | 내용 |
|-----------|----------|------|
| `behavioral-guidelines` | `**/*` | 행동 원칙 6가지 |
| `tool-usage` | `**/*` | 도구 사용 규칙, Git 안전 규칙 |
| `python-code` | `**/*.py` | 타입 안전성, 네이밍 |
| `test-writing` | `**/tests/**/*.py` | 테스트 구조, 네이밍, TDD |
| `error-classes` | `**/error.py` | 에러 클래스 계층 구조 |
| `domain` | `**/domain/**/*.py` | DDD 빌딩 블록 패턴 |
| `aspect` | `**/aspects/**/*.py` | AOP Aspect 구조 패턴 |
| `plugin` | `plugins/**/*.py` | 플러그인 개발 규칙 |
| `monorepo` | `**/pyproject.toml` | 모노레포 도구 실행 원칙 |

## 코딩 규칙 요약

상세 규칙은 [CONTRIBUTING.md](../../CONTRIBUTING.md)를 참조하세요.

- **Type Safety**: `Any` 금지, `# type: ignore` 금지
- **테스트**: 함수 기반만, `test_<function>_<scenario>_expect_<result>` 네이밍
- **에러 클래스**: `__str__` 오버라이드 금지, `AbstractSpakkyFrameworkError` 상속
- **네이밍**: Protocol은 `I` 접두사, Abstract은 `Abstract` 접두사, Error는 `Error` 접미사

## Known Issue Marker

알려진 버그를 테스트로 문서화할 때:

```python
@pytest.mark.known_issue("설명: 왜 이 동작이 잘못되었는지")
def test_feature_incorrect_behavior_expect_wrong_result() -> None:
    """현재 잘못된 동작을 문서화하는 테스트."""
    result = buggy_function()
    assert result == "wrong_but_current_behavior"
```

## 문서 유지 규칙

- 코드 변경 → 관련 문서 모두 업데이트 (CHANGELOG.md 제외, 자동 생성)
- 우선순위: Code > CONTRIBUTING.md > copilot-instructions.md > README.md

## 세션 완료 규칙

매 코딩 세션의 마지막 단계로 반드시 `harness-review` 스킬을 실행하세요.
