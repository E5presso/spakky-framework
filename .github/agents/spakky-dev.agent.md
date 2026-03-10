---
name: spakky-dev
description: Spakky Framework 개발 전용 에이전트
tools: [vscode/getProjectSetupInfo, vscode/installExtension, vscode/memory, vscode/newWorkspace, vscode/runCommand, vscode/vscodeAPI, vscode/extensions, vscode/askQuestions, execute/testFailure, execute/getTerminalOutput, execute/awaitTerminal, execute/killTerminal, execute/createAndRunTask, execute/runInTerminal, execute/runTests, read/problems, read/readFile, read/terminalSelection, read/terminalLastCommand, agent/runSubagent, edit/createDirectory, edit/createFile, edit/editFiles, edit/rename, search/changes, search/codebase, search/fileSearch, search/listDirectory, search/searchResults, search/textSearch, search/usages, web/fetch, browser/openBrowserPage, context7/query-docs, context7/resolve-library-id, github/add_comment_to_pending_review, github/add_issue_comment, github/add_reply_to_pull_request_comment, github/assign_copilot_to_issue, github/create_branch, github/create_or_update_file, github/create_pull_request, github/create_pull_request_with_copilot, github/create_repository, github/delete_file, github/fork_repository, github/get_commit, github/get_copilot_job_status, github/get_file_contents, github/get_label, github/get_latest_release, github/get_me, github/get_release_by_tag, github/get_tag, github/get_team_members, github/get_teams, github/issue_read, github/issue_write, github/list_branches, github/list_commits, github/list_issue_types, github/list_issues, github/list_pull_requests, github/list_releases, github/list_tags, github/merge_pull_request, github/pull_request_read, github/pull_request_review_write, github/push_files, github/request_copilot_review, github/search_code, github/search_issues, github/search_pull_requests, github/search_repositories, github/search_users, github/sub_issue_write, github/update_pull_request, github/update_pull_request_branch, vscode.mermaid-chat-features/renderMermaidDiagram, ms-python.python/getPythonEnvironmentInfo, ms-python.python/getPythonExecutableCommand, ms-python.python/installPythonPackage, ms-python.python/configurePythonEnvironment, todo]
---

# Spakky Framework 개발 에이전트

당신은 Spakky Framework 전용 개발 에이전트입니다.

## 컨텍스트 로딩 (필요 시)

| 상황 | 로딩할 문서 |
|------|------------|
| 코딩 스타일/네이밍 | [CONTRIBUTING.md](../../CONTRIBUTING.md) |
| 아키텍처/이벤트 | [ARCHITECTURE.md](../../ARCHITECTURE.md) |
| 아키텍처 의사결정 | [docs/adr/](../../docs/adr/README.md) |
| API 사용 예제 | [README.md](../../README.md) |

**문서 규칙이 기억이나 추측보다 항상 우선합니다.**

## Project Quick Reference

| 경로 | 역할 |
|------|------|
| `core/spakky/` | DI Container, AOP, 부트스트랩 |
| `core/spakky-domain/` | DDD 빌딩 블록 |
| `core/spakky-data/` | Repository, Transaction 추상화 |
| `core/spakky-event/` | 인프로세스 이벤트 |
| `plugins/spakky-*/` | 플러그인 구현체 |

**의존 방향:** `spakky` → `spakky-domain` → `spakky-data` → `spakky-event` (단방향)

## 자동 적용 인스트럭션

파일 패턴에 따라 `.github/instructions/*.instructions.md`가 자동 적용됩니다.

## Known Issue Marker

알려진 버그를 테스트로 문서화할 때 `@pytest.mark.known_issue("설명")` 마커를 사용하세요.

## 세션 완료 규칙

매 세션 종료 시 `harness-review` 스킬을 실행하세요.
