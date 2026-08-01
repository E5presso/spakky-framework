#!/usr/bin/env python3
"""Fail-closed Phase 5 resume routing from durable process state."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from review_receipt import (
    JsonObject,
    JsonValue,
    ReviewReceiptError,
    build_criteria_manifest,
    canonical_json,
    validate_final_review_inputs,
    validate_full_receipt,
    validate_process_state_full_receipt,
)


GIT_TIMEOUT_SECONDS = 30
HEX_DIGITS = frozenset("0123456789abcdef")
PUBLICATION_STATES = frozenset({"pending", "incomplete", "published"})

type PrDiscovery = Callable[[Path, str, str], tuple[str, list[JsonObject]]]


class Phase5ResumeError(RuntimeError):
    """Durable Phase 5 state is malformed or cannot be resumed safely."""


def _json_object(value: JsonValue, owner: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise Phase5ResumeError(f"{owner} must be a JSON object")
    return value


def _required_string(
    source: Mapping[str, JsonValue],
    key: str,
    owner: str,
) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise Phase5ResumeError(f"{owner}.{key} must be a nonblank trimmed string")
    return value


def _required_positive_integer(
    source: Mapping[str, JsonValue],
    key: str,
    owner: str,
) -> int:
    value = source.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise Phase5ResumeError(f"{owner}.{key} must be a positive integer")
    return value


def _is_git_sha(value: str) -> bool:
    return len(value) in {40, 64} and set(value) <= HEX_DIGITS


def _git(repo_root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as error:
        raise Phase5ResumeError(
            f"git {' '.join(arguments)} timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise Phase5ResumeError(
            f"git {' '.join(arguments)} failed ({completed.returncode}): {detail}"
        )
    return completed.stdout.strip()


def _git_bytes(repo_root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as error:
        raise Phase5ResumeError("git byte command timed out") from error
    if completed.returncode != 0:
        raise Phase5ResumeError(f"git byte command failed ({completed.returncode})")
    return completed.stdout


def _gh(repo_root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["gh", *arguments],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
        )
    except subprocess.TimeoutExpired as error:
        raise Phase5ResumeError(
            f"gh {' '.join(arguments)} timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise Phase5ResumeError(
            f"gh {' '.join(arguments)} failed ({completed.returncode}): {detail}"
        )
    return completed.stdout.strip()


def _optional_git_config(repo_root: Path, key: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "config", "--get", key],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as error:
        raise Phase5ResumeError(
            f"git config --get {key} timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from error
    if completed.returncode == 1 and not completed.stdout.strip():
        return None
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise Phase5ResumeError(
            f"git config --get {key} failed ({completed.returncode}): {detail}"
        )
    value = completed.stdout.strip()
    if not value:
        raise Phase5ResumeError(f"git config --get {key} returned an empty value")
    return value


def _ls_remote_push_endpoint(
    repo_root: Path,
    endpoint: str,
    current_ref: str,
) -> str:
    """Read one push endpoint without ever rendering its URL or output on error."""

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-remote",
                "--heads",
                endpoint,
                current_ref,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as error:
        raise Phase5ResumeError(
            "git ls-remote timed out for a configured push endpoint"
        ) from error
    if completed.returncode != 0:
        raise Phase5ResumeError(
            "git ls-remote failed for a configured push endpoint "
            f"({completed.returncode})"
        )
    return completed.stdout.strip()


def _live_remote_head(
    repo_root: Path,
    current_ref: str,
) -> str | None:
    branch = current_ref.removeprefix("refs/heads/")
    if not branch or branch == current_ref:
        raise Phase5ResumeError("current branch ref is not canonical")
    configured_remote = _optional_git_config(
        repo_root,
        f"branch.{branch}.remote",
    )
    remotes = set(_git(repo_root, "remote").splitlines())
    remote = "origin" if "origin" in remotes else configured_remote
    if remote is None:
        raise Phase5ResumeError(
            "origin or a configured branch remote is required for live read-back"
        )
    if remote not in remotes and remote != ".":
        raise Phase5ResumeError(
            f"configured live read-back remote is unavailable: {remote}"
        )
    raw_push_urls = _git(
        repo_root,
        "remote",
        "get-url",
        "--all",
        "--push",
        remote,
    )
    push_urls = list(dict.fromkeys(raw_push_urls.splitlines()))
    if not push_urls or any(not url.strip() or url != url.strip() for url in push_urls):
        raise Phase5ResumeError("remote has no canonical push endpoint")
    observations: list[str | None] = []
    for push_url in push_urls:
        output = _ls_remote_push_endpoint(
            repo_root,
            push_url,
            current_ref,
        )
        if not output:
            observations.append(None)
            continue
        lines = output.splitlines()
        if len(lines) != 1:
            raise Phase5ResumeError("live push endpoint returned multiple branch heads")
        fields = lines[0].split()
        if len(fields) != 2 or fields[1] != current_ref or not _is_git_sha(fields[0]):
            raise Phase5ResumeError("live push endpoint read-back is malformed")
        observations.append(fields[0])
    if any(observation != observations[0] for observation in observations[1:]):
        raise Phase5ResumeError(
            "live push endpoints disagree about the current branch head"
        )
    return observations[0]


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as error:
        raise Phase5ResumeError(
            f"git merge-base timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from error
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    detail = completed.stderr.strip() or completed.stdout.strip()
    raise Phase5ResumeError(
        f"git merge-base --is-ancestor failed ({completed.returncode}): {detail}"
    )


def _nested_repository(
    source: Mapping[str, JsonValue],
    owner: str,
) -> str:
    repository = _json_object(source.get("repo"), f"{owner}.repo")
    return _required_string(repository, "full_name", f"{owner}.repo")


def select_existing_pr(
    candidates: Sequence[Mapping[str, JsonValue]],
    *,
    repository: str,
    branch: str,
    head: str,
) -> JsonObject | None:
    """Select one exact OPEN same-repo PR or fail on ambiguous identity."""

    if not repository or repository.count("/") != 1 or repository != repository.strip():
        raise Phase5ResumeError("canonical repository identity is required")
    if not branch or branch != branch.strip() or branch.startswith("refs/"):
        raise Phase5ResumeError("canonical branch name is required")
    if not _is_git_sha(head):
        raise Phase5ResumeError("canonical PR head SHA is required")

    selected: list[JsonObject] = []
    for index, raw_candidate in enumerate(candidates):
        candidate = _json_object(dict(raw_candidate), f"PR candidate[{index}]")
        if _required_string(candidate, "state", f"PR candidate[{index}]") != "open":
            raise Phase5ResumeError("PR discovery returned a non-OPEN candidate")
        number = _required_positive_integer(
            candidate,
            "number",
            f"PR candidate[{index}]",
        )
        url = _required_string(candidate, "html_url", f"PR candidate[{index}]")
        candidate_head = _json_object(
            candidate.get("head"),
            f"PR candidate[{index}].head",
        )
        candidate_base = _json_object(
            candidate.get("base"),
            f"PR candidate[{index}].base",
        )
        head_repository = _nested_repository(
            candidate_head,
            f"PR candidate[{index}].head",
        )
        base_repository = _nested_repository(
            candidate_base,
            f"PR candidate[{index}].base",
        )
        candidate_branch = _required_string(
            candidate_head,
            "ref",
            f"PR candidate[{index}].head",
        )
        candidate_sha = _required_string(
            candidate_head,
            "sha",
            f"PR candidate[{index}].head",
        )
        if head_repository != repository or base_repository != repository:
            raise Phase5ResumeError("PR candidate is not a same-repo pull request")
        if candidate_branch != branch:
            raise Phase5ResumeError("PR candidate branch differs from current branch")
        if candidate_sha != head:
            raise Phase5ResumeError("PR candidate head differs from exact current HEAD")
        selected.append(
            {
                "number": number,
                "url": url,
                "repo": repository,
                "head_sha": head,
            }
        )
    if len(selected) > 1:
        raise Phase5ResumeError(
            "multiple OPEN same-repo exact-head PR candidates are ambiguous"
        )
    return selected[0] if selected else None


def _live_pr_discovery(
    repo_root: Path,
    branch: str,
    head: str,
) -> tuple[str, list[JsonObject]]:
    del head
    repository = _gh(
        repo_root,
        "repo",
        "view",
        "--json",
        "nameWithOwner",
        "--jq",
        ".nameWithOwner",
    )
    if not repository or repository.count("/") != 1:
        raise Phase5ResumeError("gh repo view returned invalid repository identity")
    owner = repository.split("/", maxsplit=1)[0]
    raw_pages = _gh(
        repo_root,
        "api",
        "--method",
        "GET",
        "--paginate",
        "--slurp",
        f"repos/{repository}/pulls",
        "-f",
        "state=open",
        "-f",
        f"head={owner}:{branch}",
        "-F",
        "per_page=100",
    )
    try:
        pages = json.loads(raw_pages)
    except json.JSONDecodeError as error:
        raise Phase5ResumeError("gh PR discovery returned invalid JSON") from error
    if not isinstance(pages, list):
        raise Phase5ResumeError("gh PR discovery must return paginated arrays")
    candidates: list[JsonObject] = []
    for page_index, raw_page in enumerate(pages):
        if not isinstance(raw_page, list):
            raise Phase5ResumeError(
                f"gh PR discovery page[{page_index}] must be an array"
            )
        for candidate_index, raw_candidate in enumerate(raw_page):
            candidates.append(
                _json_object(
                    raw_candidate,
                    f"gh PR discovery page[{page_index}][{candidate_index}]",
                )
            )
    return repository, candidates


def _strict_regular_file(path: Path, owner: str) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise Phase5ResumeError(f"{owner} must be an absolute regular file: {path}")
    try:
        resolved = path.resolve(strict=True)
        mode = os.lstat(resolved).st_mode
    except (FileNotFoundError, OSError) as error:
        raise Phase5ResumeError(f"{owner} is unavailable: {path}") from error
    if not stat.S_ISREG(mode):
        raise Phase5ResumeError(f"{owner} must be a regular file: {path}")
    return resolved


def _read_process_state(path: Path) -> JsonObject:
    state_path = _strict_regular_file(path, "process state")
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Phase5ResumeError(f"cannot read process state: {path}") from error
    return _json_object(value, "process state")


def _validate_pr(state: Mapping[str, JsonValue], head: str) -> JsonObject | None:
    raw_pr = state.get("pr_opened")
    if raw_pr is None:
        return None
    pr = _json_object(raw_pr, "process state.pr_opened")
    _required_positive_integer(pr, "number", "process state.pr_opened")
    _required_string(pr, "repo", "process state.pr_opened")
    _required_string(pr, "url", "process state.pr_opened")
    if _required_string(pr, "head_sha", "process state.pr_opened") != head:
        raise Phase5ResumeError("process state PR head differs from committed HEAD")
    return pr


def _validate_publication(
    state: Mapping[str, JsonValue],
    head: str,
) -> str | None:
    raw_publication = state.get("publication")
    if raw_publication is None:
        return None
    publication = _json_object(raw_publication, "process state.publication")
    state_name = _required_string(
        publication,
        "state",
        "process state.publication",
    )
    if state_name not in PUBLICATION_STATES:
        raise Phase5ResumeError(
            "process state.publication.state must be pending, incomplete, or published"
        )
    if _required_string(publication, "head_sha", "process state.publication") != head:
        raise Phase5ResumeError(
            "process state publication head differs from committed HEAD"
        )
    if state_name == "published":
        if publication.get("label_verified") is not True:
            raise Phase5ResumeError("published state must have a verified label")
        for key in ("comment_id", "status_id"):
            _required_positive_integer(publication, key, "process state.publication")
        for key in ("comment_creator", "status_creator"):
            _required_string(publication, key, "process state.publication")
    return state_name


def _push_checkpoint(
    state: Mapping[str, JsonValue],
    head: str,
    current_ref: str,
) -> bool:
    has_ref = "push_done" in state
    has_head = "push_head" in state
    if has_ref != has_head:
        raise Phase5ResumeError(
            "push_done and push_head must be recorded in the same checkpoint"
        )
    if not has_ref:
        return False
    push_ref = _required_string(state, "push_done", "process state")
    if push_ref != current_ref:
        raise Phase5ResumeError(
            "push checkpoint ref differs from the current branch ref"
        )
    push_head = _required_string(state, "push_head", "process state")
    if not _is_git_sha(push_head) or push_head != head:
        raise Phase5ResumeError("push checkpoint differs from committed HEAD")
    return True


def _fast_path_enrolled(state: Mapping[str, JsonValue]) -> bool:
    if "review_fast_path" not in state:
        return False
    marker = _json_object(
        state.get("review_fast_path"),
        "process state.review_fast_path",
    )
    if set(marker) != {"schema_version", "mode"}:
        raise Phase5ResumeError("review fast-path marker has unsupported fields")
    if marker.get("schema_version") != 1 or marker.get("mode") != (
        "exact-head-receipt"
    ):
        raise Phase5ResumeError("review fast-path marker is unsupported")
    return True


def _validate_legacy_pr(state: Mapping[str, JsonValue]) -> JsonObject | None:
    raw_pr = state.get("pr_opened")
    if raw_pr is None:
        return None
    pr = _json_object(raw_pr, "legacy process state.pr_opened")
    _required_positive_integer(pr, "number", "legacy process state.pr_opened")
    _required_string(pr, "url", "legacy process state.pr_opened")
    return pr


def _validate_block_receipt(
    state: Mapping[str, JsonValue],
    repo_root: Path,
    live_issue_body: str,
    expected_head: str,
    issue_number: int,
    *,
    require_live_criteria: bool = True,
) -> JsonObject:
    final_review = _json_object(
        state.get("final_local_review"),
        "process state.final_local_review",
    )
    manifest = _json_object(
        final_review.get("manifest"),
        "process state.final_local_review.manifest",
    )
    receipt = _json_object(
        final_review.get("receipt"),
        "process state.final_local_review.receipt",
    )
    validation_manifest = manifest
    if require_live_criteria:
        live_manifest = build_criteria_manifest(
            repo_root,
            issue_number,
            live_issue_body,
        )
        if canonical_json(manifest) != canonical_json(live_manifest):
            raise ReviewReceiptError(
                "stored criteria manifest differs from live criteria"
            )
        validation_manifest = live_manifest
    validate_full_receipt(
        receipt,
        validation_manifest,
        expected_head,
        issue_number,
    )
    if receipt.get("verdict") != "BLOCK":
        raise ReviewReceiptError("receipt is not an exact-head BLOCK")
    owner = _required_string(state, "owner", "process state")
    implementer = _required_string(state, "implementer", "process state")
    delegate = _json_object(
        state.get("final_review_delegate"),
        "process state.final_review_delegate",
    )
    reviewer = _required_string(delegate, "reviewer", "final review delegate")
    if delegate.get("head_sha") != expected_head:
        raise ReviewReceiptError("final review delegate head SHA mismatch")
    if delegate.get("criteria_digest") != manifest.get("criteria_digest"):
        raise ReviewReceiptError("final review delegate criteria digest mismatch")
    if receipt.get("owner") != owner or receipt.get("implementer") != implementer:
        raise ReviewReceiptError("BLOCK receipt owner or implementer mismatch")
    if receipt.get("reviewer") != reviewer:
        raise ReviewReceiptError("BLOCK receipt reviewer mismatch")
    expected_base_sha = _git(
        repo_root,
        "merge-base",
        "origin/develop",
        expected_head,
    )
    if receipt.get("base_sha") != expected_base_sha:
        raise ReviewReceiptError(
            "BLOCK receipt base differs from origin/develop merge-base"
        )
    expected_diff = _git_bytes(
        repo_root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--no-textconv",
        f"{expected_base_sha}...{expected_head}",
    )
    if receipt.get("diff_sha256") != hashlib.sha256(expected_diff).hexdigest():
        raise ReviewReceiptError(
            "BLOCK receipt diff digest differs from exact Git diff"
        )
    return receipt


def _validate_surviving_inputs(
    state: Mapping[str, JsonValue],
    repo_root: Path,
    live_issue_body: str,
    issue_number: int,
) -> JsonObject | None:
    if "final_review_inputs" not in state:
        return None
    try:
        inputs = validate_final_review_inputs(state, repo_root)
        live_manifest = build_criteria_manifest(
            repo_root,
            issue_number,
            live_issue_body,
        )
    except ReviewReceiptError as error:
        raise Phase5ResumeError(
            "surviving final review inputs are invalid; preserve them for diagnosis: "
            f"{error}"
        ) from error
    if inputs.get("criteria_digest") != live_manifest.get("criteria_digest"):
        raise Phase5ResumeError(
            "surviving final review inputs differ from live issue criteria; "
            "preserve them for diagnosis"
        )
    return inputs


def _result(
    *,
    mode: str,
    issue_number: int,
    head: str,
    receipt_valid: bool,
    push_checkpoint_present: bool,
    remote_exact: bool,
    build_full_required: bool,
    next_action: str,
    final_review_inputs: JsonObject | None = None,
    state_transition: JsonObject | None = None,
    pr_resolution: JsonObject | None = None,
    required_effects: Sequence[str] | None = None,
) -> JsonObject:
    result: JsonObject = {
        "schema_version": 1,
        "mode": mode,
        "issue_number": issue_number,
        "head_sha": head,
        "receipt_valid": receipt_valid,
        "push_checkpoint_present": push_checkpoint_present,
        "remote_exact": remote_exact,
        "build_full_required": build_full_required,
        "next_action": next_action,
    }
    if final_review_inputs is not None:
        result["final_review_inputs"] = final_review_inputs
    if state_transition is not None:
        result["state_transition"] = state_transition
    if pr_resolution is not None:
        result["pr_resolution"] = pr_resolution
    if required_effects is not None:
        json_effects: list[JsonValue] = []
        json_effects.extend(required_effects)
        result["required_effects"] = json_effects
    return result


def resolve_phase5_resume(
    *,
    repo_root: Path,
    process_state_path: Path,
    live_issue_body: str,
    pr_discovery: PrDiscovery | None = None,
) -> JsonObject:
    """Validate durable evidence and choose one exclusive Phase 5 resume route."""

    try:
        root = repo_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise Phase5ResumeError(
            f"repository root is unavailable: {repo_root}"
        ) from error
    if _git(root, "rev-parse", "--show-toplevel") != str(root):
        raise Phase5ResumeError("repo root must be the canonical Git worktree root")
    canonical_state_path = root / ".process-state.json"
    if process_state_path.resolve() != canonical_state_path:
        raise Phase5ResumeError(
            "process state must be the worktree .process-state.json"
        )
    state = _read_process_state(process_state_path)
    if state.get("worktree") != str(root):
        raise Phase5ResumeError("process state worktree mismatch")
    issue_number = _required_positive_integer(state, "issue_number", "process state")
    head = _git(root, "rev-parse", "HEAD")
    if not _is_git_sha(head):
        raise Phase5ResumeError("current HEAD is not a canonical Git SHA")

    if not _fast_path_enrolled(state):
        merged = state.get("merged")
        if merged is not None:
            if not isinstance(merged, str) or not _is_git_sha(merged):
                raise Phase5ResumeError("legacy merged state must be a Git SHA")
            return _result(
                mode="merged",
                issue_number=issue_number,
                head=head,
                receipt_valid=False,
                push_checkpoint_present="push_done" in state,
                remote_exact=False,
                build_full_required=False,
                next_action="none",
            )
        if _validate_legacy_pr(state) is not None:
            return _result(
                mode="legacy-resume-monitor",
                issue_number=issue_number,
                head=head,
                receipt_valid=False,
                push_checkpoint_present="push_done" in state,
                remote_exact=False,
                build_full_required=False,
                next_action="legacy-monitor-pr",
            )
        return _result(
            mode="legacy-resume-process",
            issue_number=issue_number,
            head=head,
            receipt_valid=False,
            push_checkpoint_present="push_done" in state,
            remote_exact=False,
            build_full_required=False,
            next_action="legacy-process-ticket-resume",
        )

    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise Phase5ResumeError("Phase 5 resume requires a clean committed worktree")
    current_ref = _git(root, "symbolic-ref", "--quiet", "HEAD")
    live_remote_head = _live_remote_head(root, current_ref)
    remote_exact = live_remote_head == head

    merged = state.get("merged")
    if merged is not None:
        if not isinstance(merged, str) or not _is_git_sha(merged):
            raise Phase5ResumeError("process state merged must be a Git SHA")
        commit_done = state.get("commit_done")
        if commit_done != head:
            raise Phase5ResumeError(
                "merged state commit_done differs from current HEAD"
            )
        push_checkpoint_present = _push_checkpoint(state, head, current_ref)
        if _validate_pr(state, head) is None:
            raise Phase5ResumeError("merged state requires canonical PR identity")
        if _validate_publication(state, head) != "published":
            raise Phase5ResumeError("merged state requires published review evidence")
        return _result(
            mode="merged",
            issue_number=issue_number,
            head=head,
            receipt_valid=False,
            push_checkpoint_present=push_checkpoint_present,
            remote_exact=remote_exact,
            build_full_required=False,
            next_action="none",
        )

    commit_done = state.get("commit_done")
    if commit_done is None:
        if (
            any(
                key in state
                for key in (
                    "push_done",
                    "push_head",
                    "pr_opened",
                    "publication",
                    "final_local_review",
                )
            )
            or remote_exact
        ):
            raise Phase5ResumeError("post-commit evidence exists without commit_done")
        return _result(
            mode="fresh-final-review",
            issue_number=issue_number,
            head=head,
            receipt_valid=False,
            push_checkpoint_present=False,
            remote_exact=remote_exact,
            build_full_required=True,
            next_action="record-current-head-then-run-final-review",
        )
    if not isinstance(commit_done, str) or not _is_git_sha(commit_done):
        raise Phase5ResumeError("process state commit_done must be a Git SHA")
    if commit_done != head:
        if any(
            key in state
            for key in (
                "push_done",
                "push_head",
                "pr_opened",
                "final_review_inputs",
            )
        ):
            raise Phase5ResumeError(
                "advanced HEAD coexists with push, PR, or review-input evidence"
            )
        if live_remote_head in {commit_done, head}:
            raise Phase5ResumeError(
                "old BLOCK or current advanced HEAD is already present on remote"
            )
        try:
            _validate_block_receipt(
                state,
                root,
                live_issue_body,
                commit_done,
                issue_number,
                require_live_criteria=False,
            )
        except (Phase5ResumeError, ReviewReceiptError) as error:
            raise Phase5ResumeError(
                "advanced HEAD is not backed by the prior exact-head BLOCK receipt"
            ) from error
        old_publication_state = _validate_publication(state, commit_done)
        raw_old_publication = _json_object(
            state.get("publication"),
            "process state.publication",
        )
        if (
            old_publication_state != "incomplete"
            or raw_old_publication.get("error") != "final review BLOCK"
        ):
            raise Phase5ResumeError(
                "advanced HEAD prior BLOCK publication evidence is noncanonical"
            )
        if not _is_ancestor(root, commit_done, head):
            raise Phase5ResumeError(
                "current HEAD is not a descendant of prior BLOCK commit_done"
            )
        return _result(
            mode="resume-new-head-final-review",
            issue_number=issue_number,
            head=head,
            receipt_valid=False,
            push_checkpoint_present=False,
            remote_exact=False,
            build_full_required=True,
            next_action=(
                "clear-old-head-evidence-record-current-head-then-run-final-review"
            ),
            state_transition={
                "expected_old_commit_done": commit_done,
                "set": {"commit_done": head},
                "delete": [
                    "final_local_review",
                    "final_review_delegate",
                    "publication",
                    "final_review_inputs",
                    "push_done",
                    "push_head",
                    "pr_opened",
                ],
            },
        )

    push_checkpoint_present = _push_checkpoint(state, head, current_ref)
    if push_checkpoint_present and not remote_exact:
        raise Phase5ResumeError("live remote head contradicts the push checkpoint")
    pushed_exact = remote_exact
    pr = _validate_pr(state, head)
    publication_state = _validate_publication(state, head)

    receipt_valid = False
    receipt_error: ReviewReceiptError | None = None
    try:
        validate_process_state_full_receipt(
            state,
            root,
            live_issue_body,
            head,
            issue_number,
        )
        receipt_valid = True
    except ReviewReceiptError as error:
        receipt_error = error

    if receipt_valid:
        surviving_inputs = _validate_surviving_inputs(
            state,
            root,
            live_issue_body,
            issue_number,
        )
        if surviving_inputs is not None:
            return _result(
                mode="resume-cleanup-final-review-inputs",
                issue_number=issue_number,
                head=head,
                receipt_valid=True,
                push_checkpoint_present=push_checkpoint_present,
                remote_exact=remote_exact,
                build_full_required=False,
                next_action="cleanup-final-review-inputs-then-rerun-resolver",
                final_review_inputs=surviving_inputs,
                state_transition={
                    "command": "review_receipt.py cleanup-inputs",
                    "receipt_verdict": "PASS",
                    "after": "rerun-resolver",
                },
            )

    if not receipt_valid:
        block_receipt: JsonObject | None = None
        if "final_local_review" in state:
            try:
                block_receipt = _validate_block_receipt(
                    state,
                    root,
                    live_issue_body,
                    head,
                    issue_number,
                )
            except ReviewReceiptError:
                block_receipt = None
        if block_receipt is not None:
            raw_publication = _json_object(
                state.get("publication"),
                "process state.publication",
            )
            block_state_valid = (
                publication_state == "incomplete"
                and raw_publication.get("error") == "final review BLOCK"
            )
            if pushed_exact or pr is not None or not block_state_valid:
                raise Phase5ResumeError(
                    "exact-head BLOCK receipt cannot coexist with push, PR, or "
                    "noncanonical publication evidence"
                )
            surviving_inputs = _validate_surviving_inputs(
                state,
                root,
                live_issue_body,
                issue_number,
            )
            if surviving_inputs is not None:
                return _result(
                    mode="resume-cleanup-blocked-review-inputs",
                    issue_number=issue_number,
                    head=head,
                    receipt_valid=False,
                    push_checkpoint_present=False,
                    remote_exact=False,
                    build_full_required=False,
                    next_action=("cleanup-final-review-inputs-then-return-to-phase4"),
                    final_review_inputs=surviving_inputs,
                    state_transition={
                        "command": "review_receipt.py cleanup-inputs",
                        "receipt_verdict": "BLOCK",
                        "after": "return-to-phase4",
                    },
                )
            return _result(
                mode="resume-phase4-after-block",
                issue_number=issue_number,
                head=head,
                receipt_valid=False,
                push_checkpoint_present=False,
                remote_exact=False,
                build_full_required=False,
                next_action="return-to-phase4-fix-commit-new-full-review",
            )

        surviving_inputs = _validate_surviving_inputs(
            state,
            root,
            live_issue_body,
            issue_number,
        )
        if surviving_inputs is not None:
            if pushed_exact or pr is not None or publication_state is not None:
                raise Phase5ResumeError(
                    "unconsumed final review inputs coexist with post-review or "
                    "push evidence; preserve them for diagnosis"
                )
            return _result(
                mode="resume-final-review-inputs",
                issue_number=issue_number,
                head=head,
                receipt_valid=False,
                push_checkpoint_present=False,
                remote_exact=False,
                build_full_required=True,
                next_action="rehydrate-final-review-inputs",
                final_review_inputs=surviving_inputs,
            )

        if pushed_exact or pr is not None or publication_state is not None:
            detail = (
                str(receipt_error) if receipt_error is not None else "missing receipt"
            )
            raise Phase5ResumeError(
                "post-review or push evidence exists without a publishable exact-head "
                f"receipt: {detail}"
            ) from receipt_error
        return _result(
            mode="fresh-final-review",
            issue_number=issue_number,
            head=head,
            receipt_valid=False,
            push_checkpoint_present=False,
            remote_exact=remote_exact,
            build_full_required=True,
            next_action="run-final-review-and-build-full",
        )

    if pr is None:
        if publication_state not in {None, "pending"}:
            raise Phase5ResumeError(
                "publication cannot be incomplete or published before PR identity"
            )
        pr_resolution: JsonObject | None = None
        if remote_exact:
            branch = current_ref.removeprefix("refs/heads/")
            discovery = pr_discovery or _live_pr_discovery
            repository, candidates = discovery(root, branch, head)
            existing_pr = select_existing_pr(
                candidates,
                repository=repository,
                branch=branch,
                head=head,
            )
            if existing_pr is None:
                pr_resolution = {
                    "action": "create",
                    "repository": repository,
                    "branch": branch,
                    "head_sha": head,
                    "gh_pr_create_allowed": True,
                    "metadata_convergence_required": True,
                }
                pr_action = "create-pr-converge-metadata-record-pr-checkpoint"
            else:
                pr_resolution = {
                    "action": "adopt",
                    "pr_opened": existing_pr,
                    "gh_pr_create_allowed": False,
                    "metadata_convergence_required": True,
                }
                pr_action = "adopt-existing-pr-converge-metadata-record-pr-checkpoint"
            next_action = (
                pr_action
                if push_checkpoint_present
                else f"record-push-checkpoint-then-{pr_action}"
            )
        else:
            next_action = "push-readback-record-checkpoint-then-create-or-adopt-pr"
        return _result(
            mode="resume-push-or-create-pr",
            issue_number=issue_number,
            head=head,
            receipt_valid=True,
            push_checkpoint_present=push_checkpoint_present,
            remote_exact=remote_exact,
            build_full_required=False,
            next_action=next_action,
            pr_resolution=pr_resolution,
        )

    if not pushed_exact:
        raise Phase5ResumeError(
            "PR identity exists without an exact-head push checkpoint or remote read-back"
        )
    if publication_state is None:
        raise Phase5ResumeError("PR identity exists without publication state")
    publication_action = (
        "revalidate-live-pr-replay-in-review-then-publish"
        if push_checkpoint_present
        else (
            "record-push-checkpoint-then-revalidate-live-pr-replay-in-review-"
            "then-publish"
        )
    )
    return _result(
        mode="resume-in-review-publication",
        issue_number=issue_number,
        head=head,
        receipt_valid=True,
        push_checkpoint_present=push_checkpoint_present,
        remote_exact=remote_exact,
        build_full_required=False,
        next_action=publication_action,
        required_effects=[
            "live-pr-identity-readback",
            "project-status-in-review",
            "receipt-publisher",
            "live-publication-readback",
        ],
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve a fail-closed Phase 5 resume route.",
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--process-state", type=Path, required=True)
    parser.add_argument("--issue-body-file", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        issue_body_path = _strict_regular_file(
            arguments.issue_body_file,
            "live issue body",
        )
        live_issue_body = issue_body_path.read_text(encoding="utf-8")
        result = resolve_phase5_resume(
            repo_root=arguments.repo_root,
            process_state_path=arguments.process_state,
            live_issue_body=live_issue_body,
        )
    except (OSError, UnicodeError, Phase5ResumeError) as error:
        print(f"phase5-resume-error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
