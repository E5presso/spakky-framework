#!/usr/bin/env python3
"""Deterministically publish an already-validated exact-head review receipt."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import cast, override


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
RECEIPT_SCRIPT_DIRECTORY = REPOSITORY_ROOT / ".agents/skills/process-ticket/scripts"
sys.path.insert(0, str(RECEIPT_SCRIPT_DIRECTORY))
from review_receipt import (  # noqa: E402 - sibling skill scripts are not a package
    JsonObject,
    JsonValue,
    ReviewReceiptError,
    validate_process_state_full_receipt,
)


AI_REVIEW_CONTEXT = "ai-review"
AUTO_APPROVABLE_LABEL = "auto-approvable"
TRUSTED_ROLES = frozenset({"admin", "maintain"})


class PublicationError(RuntimeError):
    """Publication cannot safely continue."""


class CommandError(PublicationError):
    """A git or GitHub command failed."""


class ICommandRunner(ABC):
    """Injectable command boundary for offline contract tests."""

    @abstractmethod
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> str:
        """Run one command and return stdout."""


class SubprocessCommandRunner(ICommandRunner):
    """Production command runner."""

    @override
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> str:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            rendered = " ".join(argv)
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise CommandError(
                f"command failed ({completed.returncode}): {rendered}: {detail}"
            )
        return completed.stdout


ReceiptValidator = Callable[
    [Mapping[str, JsonValue], Path, str, str, int],
    JsonObject,
]


@dataclass(frozen=True)
class PublicationContext:
    repo_root: Path
    process_state_path: Path
    process_state: JsonObject
    repository: str
    issue_number: int
    pr_number: int
    pr_url: str
    head_sha: str
    receipt: JsonObject


@dataclass(frozen=True)
class CommentSurface:
    identifier: int
    url: str
    creator: str


@dataclass(frozen=True)
class StatusSurface:
    identifier: int
    creator: str
    reused: bool


def _json_object(value: object, name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise PublicationError(f"{name} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise PublicationError(f"{name} must use string keys")
    return cast(JsonObject, value)


def _required_string(source: Mapping[str, object], key: str, owner: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise PublicationError(f"{owner}.{key} must be a non-empty string")
    return value


def _required_integer(source: Mapping[str, object], key: str, owner: str) -> int:
    value = source.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PublicationError(f"{owner}.{key} must be a positive integer")
    return value


def _run_json(
    runner: ICommandRunner,
    argv: Sequence[str],
    *,
    cwd: Path,
    input_value: object | None = None,
) -> object:
    input_text = None
    if input_value is not None:
        input_text = json.dumps(
            input_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    raw = runner.run(argv, cwd=cwd, input_text=input_text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise PublicationError(
            f"invalid JSON from command: {' '.join(argv)}"
        ) from error


def _read_process_state(path: Path) -> JsonObject:
    if not path.is_file() or path.is_symlink():
        raise PublicationError(f"process state must be a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError(f"cannot read process state: {path}") from error
    return _json_object(value, "process state")


def _write_process_state(path: Path, state: Mapping[str, JsonValue]) -> None:
    serialized = (
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if path.read_text(encoding="utf-8") == serialized:
        return
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)


def _set_publication(
    context: PublicationContext,
    *,
    state_name: str,
    comment: CommentSurface | None = None,
    label_verified: bool = False,
    status: StatusSurface | None = None,
    error: str | None = None,
) -> None:
    state = dict(context.process_state)
    publication: JsonObject = {
        "state": state_name,
        "head_sha": context.head_sha,
        "comment_id": comment.identifier if comment else None,
        "comment_url": comment.url if comment else None,
        "comment_creator": comment.creator if comment else None,
        "label_verified": label_verified,
        "status_id": status.identifier if status else None,
        "status_creator": status.creator if status else None,
        "status_reused": status.reused if status else None,
    }
    if error is not None:
        publication["error"] = error
    state["publication"] = publication
    _write_process_state(context.process_state_path, state)
    context.process_state.clear()
    context.process_state.update(state)


def _repository_root(runner: ICommandRunner) -> Path:
    raw = runner.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=Path.cwd(),
    ).strip()
    if not raw:
        raise PublicationError("git repository root is empty")
    return Path(raw).resolve()


def _git_output(
    runner: ICommandRunner,
    repo_root: Path,
    *arguments: str,
) -> str:
    return runner.run(
        ("git", "-C", str(repo_root), *arguments),
        cwd=repo_root,
    ).strip()


def _assert_git_alignment(
    runner: ICommandRunner,
    context: PublicationContext,
) -> None:
    dirty = _git_output(
        runner,
        context.repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if dirty:
        raise PublicationError("worktree is dirty")
    local_head = _git_output(runner, context.repo_root, "rev-parse", "HEAD")
    upstream_head = _git_output(
        runner,
        context.repo_root,
        "rev-parse",
        "@{upstream}",
    )
    if local_head != context.head_sha:
        raise PublicationError("local HEAD drift")
    if upstream_head != context.head_sha:
        raise PublicationError("upstream drift")


def _runtime_repository(runner: ICommandRunner, repo_root: Path) -> str:
    value = _json_object(
        _run_json(
            runner,
            ("gh", "repo", "view", "--json", "nameWithOwner"),
            cwd=repo_root,
        ),
        "gh repo view",
    )
    repository = _required_string(value, "nameWithOwner", "repository")
    if repository.count("/") != 1:
        raise PublicationError(f"invalid canonical repository: {repository}")
    return repository


def _fetch_issue(runner: ICommandRunner, context: PublicationContext) -> str:
    value = _json_object(
        _run_json(
            runner,
            (
                "gh",
                "api",
                f"repos/{context.repository}/issues/{context.issue_number}",
            ),
            cwd=context.repo_root,
        ),
        "live issue",
    )
    if _required_integer(value, "number", "live issue") != context.issue_number:
        raise PublicationError("live issue number mismatch")
    body = value.get("body")
    if not isinstance(body, str):
        raise PublicationError("live issue.body must be a string")
    return body


def _fetch_pr(
    runner: ICommandRunner,
    context: PublicationContext,
) -> JsonObject:
    value = _json_object(
        _run_json(
            runner,
            (
                "gh",
                "api",
                f"repos/{context.repository}/pulls/{context.pr_number}",
            ),
            cwd=context.repo_root,
        ),
        "live PR",
    )
    if _required_integer(value, "number", "live PR") != context.pr_number:
        raise PublicationError("live PR number mismatch")
    if value.get("state") != "open":
        raise PublicationError("live PR is not open")
    if value.get("draft") is not False:
        raise PublicationError("live PR is draft or draft state is missing")
    if _required_string(value, "html_url", "live PR") != context.pr_url:
        raise PublicationError("live PR URL mismatch")
    head = _json_object(value.get("head"), "live PR.head")
    base = _json_object(value.get("base"), "live PR.base")
    if _required_string(head, "sha", "live PR.head") != context.head_sha:
        raise PublicationError("live PR head mismatch")
    head_repo = _json_object(head.get("repo"), "live PR.head.repo")
    base_repo = _json_object(base.get("repo"), "live PR.base.repo")
    head_name = _required_string(head_repo, "full_name", "live PR.head.repo")
    base_name = _required_string(base_repo, "full_name", "live PR.base.repo")
    if head_name != context.repository or base_name != context.repository:
        raise PublicationError("live PR is not same-repository")
    return value


def _basic_receipt_gate(
    state: Mapping[str, object],
    head_sha: str,
) -> JsonObject:
    final_review = _json_object(
        state.get("final_local_review"),
        "process state.final_local_review",
    )
    receipt = _json_object(final_review.get("receipt"), "final receipt")
    if receipt.get("mode") != "full":
        raise PublicationError("delta receipt is not publishable")
    if receipt.get("verdict") != "PASS":
        raise PublicationError("only PASS receipt is publishable")
    if receipt.get("head_sha") != head_sha:
        raise PublicationError("receipt head is stale")
    rows = receipt.get("rows")
    if not isinstance(rows, list) or len(rows) != 14:
        raise PublicationError("final receipt must contain 14 rows")
    if any(
        not isinstance(row, dict) or row.get("disposition") != "reverified"
        for row in rows
    ):
        raise PublicationError("final receipt must be 14/14 reverified")
    return receipt


def _preflight(
    pr_number: int,
    process_state_path: Path,
    runner: ICommandRunner,
    validator: ReceiptValidator,
) -> PublicationContext:
    repo_root = _repository_root(runner)
    canonical_state_path = process_state_path.resolve()
    if canonical_state_path != repo_root / ".process-state.json":
        raise PublicationError(
            "process state path must be the worktree .process-state.json"
        )
    state = _read_process_state(canonical_state_path)
    if state.get("worktree") != str(repo_root):
        raise PublicationError("process state worktree mismatch")
    dirty = _git_output(
        runner,
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if dirty:
        raise PublicationError("worktree is dirty")
    head_sha = _git_output(runner, repo_root, "rev-parse", "HEAD")
    commit_done = _required_string(state, "commit_done", "process state")
    push_head = _required_string(state, "push_head", "process state")
    upstream_head = _git_output(runner, repo_root, "rev-parse", "@{upstream}")
    if len({head_sha, commit_done, push_head, upstream_head}) != 1:
        raise PublicationError("local/commit/push/upstream exact-head alignment failed")
    repository = _runtime_repository(runner, repo_root)
    issue_number = _required_integer(state, "issue_number", "process state")
    stored_pr = _json_object(state.get("pr_opened"), "process state.pr_opened")
    if _required_string(stored_pr, "repo", "process state.pr_opened") != repository:
        raise PublicationError("stored PR repository mismatch")
    if _required_integer(stored_pr, "number", "process state.pr_opened") != pr_number:
        raise PublicationError("stored PR number mismatch")
    pr_url = _required_string(stored_pr, "url", "process state.pr_opened")
    stored_head = _required_string(
        stored_pr,
        "head_sha",
        "process state.pr_opened",
    )
    if stored_head != head_sha:
        raise PublicationError("stored PR head mismatch")
    provisional = PublicationContext(
        repo_root=repo_root,
        process_state_path=canonical_state_path,
        process_state=state,
        repository=repository,
        issue_number=issue_number,
        pr_number=pr_number,
        pr_url=pr_url,
        head_sha=head_sha,
        receipt=_basic_receipt_gate(state, head_sha),
    )
    live_issue_body = _fetch_issue(runner, provisional)
    validated = validator(
        state,
        repo_root,
        live_issue_body,
        head_sha,
        issue_number,
    )
    receipt = _json_object(validated, "validated receipt")
    _fetch_pr(runner, provisional)
    return PublicationContext(
        repo_root=provisional.repo_root,
        process_state_path=provisional.process_state_path,
        process_state=provisional.process_state,
        repository=provisional.repository,
        issue_number=provisional.issue_number,
        pr_number=provisional.pr_number,
        pr_url=provisional.pr_url,
        head_sha=provisional.head_sha,
        receipt=receipt,
    )


def _receipt_marker(context: PublicationContext) -> str:
    criteria_digest = _required_string(
        context.receipt,
        "criteria_digest",
        "final receipt",
    )
    matrix_digest = _required_string(
        context.receipt,
        "matrix_digest",
        "final receipt",
    )
    result_digest = _required_string(
        context.receipt,
        "result_digest",
        "final receipt",
    )
    return (
        "<!-- ai-review receipt=full-pass "
        f"head={context.head_sha} criteria={criteria_digest} "
        f"matrix={matrix_digest} result={result_digest} -->"
    )


def _comment_body(context: PublicationContext) -> str:
    reviewer = _required_string(context.receipt, "reviewer", "final receipt")
    return "\n".join(
        (
            "## AI 리뷰 결과: 자동 승인 가능",
            "",
            "- 최종 판정: PASS",
            f"- 검증 HEAD: {context.head_sha}",
            "- 검증 범주: C01–C14 14/14 독립 재검증",
            f"- 독립 reviewer: {reviewer}",
            "- blocker: 0",
            "",
            _receipt_marker(context),
            f"<!-- ai-review verdict=AUTO_APPROVE head={context.head_sha} -->",
        )
    )


def _paginated_objects(
    runner: ICommandRunner,
    context: PublicationContext,
    endpoint: str,
    name: str,
) -> list[JsonObject]:
    value = _run_json(
        runner,
        ("gh", "api", "--paginate", "--slurp", endpoint),
        cwd=context.repo_root,
    )
    if not isinstance(value, list):
        raise PublicationError(f"{name} pagination must return a list")
    flattened: list[object] = []
    if value and all(isinstance(page, list) for page in value):
        for page in value:
            flattened.extend(cast(list[object], page))
    else:
        flattened = cast(list[object], value)
    return [_json_object(item, name) for item in flattened]


def _canonical_comment(
    runner: ICommandRunner,
    context: PublicationContext,
    comments: Sequence[Mapping[str, object]],
    expected_body: str,
) -> CommentSurface | None:
    matching: list[CommentSurface] = []
    roles: dict[str, str] = {}
    for comment in comments:
        body = comment.get("body")
        if body != expected_body:
            continue
        user = _json_object(comment.get("user"), "comment.user")
        login = _required_string(user, "login", "comment.user")
        if login not in roles:
            roles[login] = _permission(runner, context, login)
        if roles[login] not in TRUSTED_ROLES:
            continue
        matching.append(
            CommentSurface(
                _required_integer(comment, "id", "comment"),
                _required_string(comment, "html_url", "comment"),
                login,
            )
        )
    return max(matching, key=lambda item: item.identifier, default=None)


def _list_comments(
    runner: ICommandRunner,
    context: PublicationContext,
) -> list[JsonObject]:
    return _paginated_objects(
        runner,
        context,
        (
            f"repos/{context.repository}/issues/{context.pr_number}"
            "/comments?per_page=100"
        ),
        "PR comments",
    )


def _ensure_comment(
    runner: ICommandRunner,
    context: PublicationContext,
) -> CommentSurface:
    expected_body = _comment_body(context)
    canonical = _canonical_comment(
        runner,
        context,
        _list_comments(runner, context),
        expected_body,
    )
    if canonical is not None:
        return canonical
    actor = _authenticated_actor(runner, context)
    if _permission(runner, context, actor) not in TRUSTED_ROLES:
        raise PublicationError("publisher actor role is not admin or maintain")
    _run_json(
        runner,
        (
            "gh",
            "api",
            "-X",
            "POST",
            (f"repos/{context.repository}/issues/{context.pr_number}/comments"),
            "--input",
            "-",
        ),
        cwd=context.repo_root,
        input_value={"body": expected_body},
    )
    canonical = _canonical_comment(
        runner,
        context,
        _list_comments(runner, context),
        expected_body,
    )
    if canonical is None:
        raise PublicationError("receipt comment read-back failed")
    return canonical


def _has_label(pr: Mapping[str, object]) -> bool:
    labels = pr.get("labels")
    if not isinstance(labels, list):
        raise PublicationError("live PR.labels must be a list")
    return any(
        _json_object(label, "live PR label").get("name") == AUTO_APPROVABLE_LABEL
        for label in labels
    )


def _ensure_label(
    runner: ICommandRunner,
    context: PublicationContext,
) -> None:
    if not _has_label(_fetch_pr(runner, context)):
        _run_json(
            runner,
            (
                "gh",
                "api",
                "-X",
                "POST",
                f"repos/{context.repository}/issues/{context.pr_number}/labels",
                "--input",
                "-",
            ),
            cwd=context.repo_root,
            input_value={"labels": [AUTO_APPROVABLE_LABEL]},
        )
    if not _has_label(_fetch_pr(runner, context)):
        raise PublicationError("auto-approvable label read-back failed")


def _recheck_commit_point(
    runner: ICommandRunner,
    context: PublicationContext,
    validator: ReceiptValidator,
) -> None:
    _assert_git_alignment(runner, context)
    live_issue_body = _fetch_issue(runner, context)
    validator(
        context.process_state,
        context.repo_root,
        live_issue_body,
        context.head_sha,
        context.issue_number,
    )
    _fetch_pr(runner, context)


def _list_statuses(
    runner: ICommandRunner,
    context: PublicationContext,
) -> list[JsonObject]:
    statuses = _paginated_objects(
        runner,
        context,
        (
            f"repos/{context.repository}/commits/{context.head_sha}"
            "/statuses?per_page=100"
        ),
        "commit statuses",
    )
    return [status for status in statuses if status.get("context") == AI_REVIEW_CONTEXT]


def _permission(
    runner: ICommandRunner,
    context: PublicationContext,
    login: str,
) -> str:
    if not login or "/" in login:
        raise PublicationError(f"invalid collaborator login: {login!r}")
    value = _json_object(
        _run_json(
            runner,
            (
                "gh",
                "api",
                (f"repos/{context.repository}/collaborators/{login}/permission"),
            ),
            cwd=context.repo_root,
        ),
        "collaborator permission",
    )
    return _required_string(value, "role_name", "collaborator permission")


def _authenticated_actor(
    runner: ICommandRunner,
    context: PublicationContext,
) -> str:
    actor_value = _json_object(
        _run_json(runner, ("gh", "api", "user"), cwd=context.repo_root),
        "authenticated actor",
    )
    return _required_string(actor_value, "login", "authenticated actor")


def _status_snapshot(
    runner: ICommandRunner,
    context: PublicationContext,
) -> tuple[
    tuple[int, str, str] | None,
    tuple[int, str, str] | None,
]:
    parsed: list[tuple[int, str, str]] = []
    seen_ids: set[int] = set()
    roles: dict[str, str] = {}
    for status in _list_statuses(runner, context):
        identifier = _required_integer(status, "id", "status")
        if identifier in seen_ids:
            raise PublicationError(f"duplicate status id: {identifier}")
        seen_ids.add(identifier)
        creator = _json_object(status.get("creator"), "status.creator")
        login = _required_string(creator, "login", "status.creator")
        status_state = _required_string(status, "state", "status")
        if login not in roles:
            roles[login] = _permission(runner, context, login)
        parsed.append((identifier, status_state, login))
    overall = max(parsed, key=lambda item: item[0], default=None)
    trusted = [item for item in parsed if roles[item[2]] in TRUSTED_ROLES]
    latest_trusted = max(trusted, key=lambda item: item[0], default=None)
    return overall, latest_trusted


def _ensure_status(
    runner: ICommandRunner,
    context: PublicationContext,
) -> StatusSurface:
    overall, latest_trusted = _status_snapshot(runner, context)
    if latest_trusted is not None and latest_trusted[1] != "success":
        raise PublicationError("latest trusted ai-review status is not success")
    if latest_trusted is not None and overall == latest_trusted:
        return StatusSurface(latest_trusted[0], latest_trusted[2], True)
    actor = _authenticated_actor(runner, context)
    if _permission(runner, context, actor) not in TRUSTED_ROLES:
        raise PublicationError("publisher actor role is not admin or maintain")
    posted = _json_object(
        _run_json(
            runner,
            (
                "gh",
                "api",
                "-X",
                "POST",
                f"repos/{context.repository}/statuses/{context.head_sha}",
                "--input",
                "-",
            ),
            cwd=context.repo_root,
            input_value={
                "context": AI_REVIEW_CONTEXT,
                "description": "AI review receipt: full PASS",
                "state": "success",
                "target_url": context.pr_url,
            },
        ),
        "posted status",
    )
    return StatusSurface(
        _required_integer(posted, "id", "posted status"),
        actor,
        False,
    )


def _postflight(
    runner: ICommandRunner,
    context: PublicationContext,
    validator: ReceiptValidator,
    selected_status: StatusSurface,
) -> CommentSurface:
    _recheck_commit_point(runner, context, validator)
    if not _has_label(_fetch_pr(runner, context)):
        raise PublicationError("postflight label verification failed")
    comment = _canonical_comment(
        runner,
        context,
        _list_comments(runner, context),
        _comment_body(context),
    )
    if comment is None:
        raise PublicationError("postflight comment verification failed")
    overall, latest_trusted = _status_snapshot(runner, context)
    if (
        overall is None
        or latest_trusted is None
        or overall[0] != selected_status.identifier
        or latest_trusted[0] != selected_status.identifier
        or latest_trusted[1] != "success"
    ):
        raise PublicationError(
            "postflight latest overall status is not selected trusted success"
        )
    return comment


def publish_final_review(
    *,
    pr_number: int,
    process_state_path: Path,
    runner: ICommandRunner,
    validator: ReceiptValidator = validate_process_state_full_receipt,
) -> PublicationContext:
    """Publish a full receipt; never review or fall back."""

    context = _preflight(
        pr_number,
        process_state_path,
        runner,
        validator,
    )
    current = context.process_state.get("publication")
    already_published = (
        isinstance(current, dict)
        and current.get("state") == "published"
        and current.get("head_sha") == context.head_sha
    )
    if not already_published:
        _set_publication(context, state_name="pending")
    comment: CommentSurface | None = None
    label_verified = False
    status: StatusSurface | None = None
    try:
        comment = _ensure_comment(runner, context)
        _ensure_label(runner, context)
        label_verified = True
        _recheck_commit_point(runner, context, validator)
        status = _ensure_status(runner, context)
        comment = _postflight(runner, context, validator, status)
    except (CommandError, PublicationError, ReviewReceiptError) as error:
        _set_publication(
            context,
            state_name="incomplete",
            comment=comment,
            label_verified=label_verified,
            status=status,
            error=str(error),
        )
        raise
    _set_publication(
        context,
        state_name="published",
        comment=comment,
        label_verified=True,
        status=status,
    )
    return context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish an exact-head final review receipt.",
    )
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--process-state", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.pr < 1:
        print("publish-final-review: --pr must be positive", file=sys.stderr)
        return 2
    try:
        context = publish_final_review(
            pr_number=arguments.pr,
            process_state_path=arguments.process_state,
            runner=SubprocessCommandRunner(),
        )
    except (CommandError, PublicationError, ReviewReceiptError) as error:
        print(f"publish-final-review: failed: {error}", file=sys.stderr)
        return 2
    publication = _json_object(
        context.process_state.get("publication"),
        "publication",
    )
    print("publish-final-review: published")
    print(f"pr: #{context.pr_number} ({context.pr_url})")
    print(f"head: {context.head_sha}")
    print(f"comment: {publication.get('comment_url')}")
    print(f"status-id: {publication.get('status_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
