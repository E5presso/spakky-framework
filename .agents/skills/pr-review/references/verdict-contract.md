# `/pr-review` verdict contract

The reviewer subagent must return exactly one JSON object:

```json
{
  "verdict": "AUTO_APPROVE",
  "head_sha": "40-char git SHA",
  "comment_body": "Korean Markdown comment ending with <!-- ai-review verdict=AUTO_APPROVE head=<HEAD_SHA> -->",
  "blocking_findings": [],
  "reviewed_categories": [
    "아키텍처 엄수",
    "타입 규율"
  ]
}
```

## Field rules

- `verdict` is exactly one of `AUTO_APPROVE`, `CHANGES_REQUESTED`, `HUMAN_REVIEW`.
- `head_sha` equals the PR metadata `headRefOid`.
- `comment_body` is ready to post as-is. The orchestrator will not rewrite it.
- `blocking_findings` contains only P0/P1 or repo-policy merge blockers. If there are no blockers, use an empty array.
- `reviewed_categories` lists every category from `.agents/skills/review-code/SKILL.md`. If the actual category count differs from this example, include every category from the actual file.
- `AUTO_APPROVE` is valid only when `blocking_findings` is an empty array and `reviewed_categories` includes every actual review-code category. If either condition is false, choose `CHANGES_REQUESTED` or `HUMAN_REVIEW`.

## Comment shape

Use Korean and one of these headings:

- `## AI 리뷰 결과: 자동 승인 가능`
- `## AI 리뷰 결과: 변경 요청`
- `## AI 리뷰 결과: 사람 검토 필요`

For `CHANGES_REQUESTED`, include the blocking findings as bullets with `file:line` when available.

For `AUTO_APPROVE`, state that no P0/P1 blockers were found under the loaded repo review criteria.

For `HUMAN_REVIEW`, state why automatic approval is not appropriate even though no P0/P1 blocker was confirmed.

Always end with the exact marker:

```html
<!-- ai-review verdict=<VERDICT> head=<HEAD_SHA> -->
```
