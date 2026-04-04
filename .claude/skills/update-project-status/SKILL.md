---
name: update-project-status
description: GitHub Issue에 연결된 프로젝트의 Status 필드를 갱신합니다.
argument-hint: "<issue-number> <status>"
user-invocable: false
---

# Update Project Status — 프로젝트 상태 자동 갱신

GitHub Issue에 연결된 프로젝트(ProjectV2)의 Status 필드를 갱신한다.
연결된 프로젝트가 없거나 Status 필드가 없으면 조용히 건너뛴다.

## 인자

`$ARGUMENTS`를 파싱한다:

- 첫 번째: Issue 번호 (예: `42`, `#42`)
- 두 번째: 목표 Status 값 (예: `In Progress`, `In Review`, `Done`)

## 절차

### 1. 프로젝트 항목 조회

이슈에 연결된 프로젝트 항목과 Status 필드 정보를 조회한다.

```bash
gh api graphql -f query='
  query($owner: String!, $repo: String!, $issueNumber: Int!) {
    repository(owner: $owner, name: $repo) {
      issue(number: $issueNumber) {
        projectItems(first: 10) {
          nodes {
            id
            project {
              id
              title
              field(name: "Status") {
                ... on ProjectV2SingleSelectField {
                  id
                  options { id name }
                }
              }
            }
          }
        }
      }
    }
  }
' -F owner={OWNER} -F repo={REPO} -F issueNumber=$ISSUE_NUMBER
```

- `owner`와 `repo`는 현재 리포지토리에서 `gh repo view --json owner,name`으로 얻는다.
- `projectItems.nodes`가 비어있으면 "연결된 프로젝트 없음"을 출력하고 종료한다.

### 2. 옵션 매칭

각 프로젝트 항목에 대해:

1. `project.field`가 null이면 (Status 필드 없음) 해당 프로젝트를 건너뛴다.
2. `field.options`에서 목표 Status와 이름이 일치하는 옵션 ID를 찾는다.
3. 일치하는 옵션이 없으면 해당 프로젝트를 건너뛴다.

### 3. 상태 갱신

매칭된 각 프로젝트에 대해 mutation을 실행한다:

```bash
gh api graphql -f query='
  mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
    updateProjectV2ItemFieldValue(
      input: {
        projectId: $projectId
        itemId: $itemId
        fieldId: $fieldId
        value: { singleSelectOptionId: $optionId }
      }
    ) {
      projectV2Item { id }
    }
  }
' -f projectId="$PROJECT_ID" -f itemId="$ITEM_ID" -f fieldId="$FIELD_ID" -f optionId="$OPTION_ID"
```

### 4. 결과 보고

- 갱신 성공: `프로젝트 "{프로젝트명}" 상태 -> {STATUS}` 출력
- 갱신 실패: 경고만 출력하고 호출자의 흐름을 중단하지 않는다.
- 스킵된 프로젝트가 있으면 사유를 간결히 출력한다.

## 규칙

- 이 스킬은 실패해도 호출자의 Phase 진행을 차단하지 않는다.
- GraphQL 호출 실패 시 1회 재시도 후 포기한다.
- `gh auth status`에 `project` scope가 없으면 경고를 출력하고 종료한다.

$ARGUMENTS
