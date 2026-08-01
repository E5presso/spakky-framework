#!/usr/bin/env python3
"""Executable contract checks for fail-closed Phase 5 resume routing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory, mkdtemp
from unittest.mock import patch


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIRECTORY))
from resolve_phase5_resume import (  # noqa: E402 - contract imports sibling script
    _ls_remote_push_endpoint,
    Phase5ResumeError,
    resolve_phase5_resume,
    select_existing_pr,
)
from review_receipt import (  # noqa: E402 - contract imports sibling script
    CATEGORY_IDS,
    JsonObject,
    JsonValue,
    build_criteria_manifest,
    cleanup_final_review_inputs,
    compute_matrix_digest,
    compute_result_digest,
)


ISSUE_NUMBER = 527
ISSUE_BODY = "# Phase 5 resume\n\nPreserve exact-head review evidence.\n"
OWNER = "owner"
IMPLEMENTER = "implementer"
REVIEWER = "independent-reviewer"


def _isolate_fixture_git_environment() -> None:
    """Prevent an outer pre-commit process from lending its index to fixtures."""
    for variable in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_WORK_TREE",
    ):
        os.environ.pop(variable, None)
    os.environ["PRE_COMMIT_ALLOW_NO_CONFIG"] = "1"


def _run(*arguments: str, cwd: Path) -> str:
    completed = subprocess.run(
        [*arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{' '.join(arguments)} failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _initialize_repository(repo_root: Path, remote_root: Path) -> tuple[str, str]:
    repo_root.mkdir()
    _run("git", "init", "--bare", str(remote_root), cwd=repo_root.parent)
    _run("git", "init", "-b", "feat/527", cwd=repo_root)
    _run("git", "config", "user.name", "Contract", cwd=repo_root)
    _run("git", "config", "user.email", "contract@example.com", cwd=repo_root)
    _run("git", "config", "core.hooksPath", "/dev/null", cwd=repo_root)
    _write(repo_root / ".gitignore", ".process-state.json\n")
    _write(repo_root / "AGENTS.md", "# Agent contract\n")
    _write(
        repo_root / ".agents/skills/review-code/SKILL.md",
        "# Review code\n",
    )
    _write(repo_root / ".agents/rules/rules.md", "# Review rules\n")
    policy = {
        "schema_version": 1,
        "categories": list(CATEGORY_IDS),
        "sources": [
            ".agents/review-criteria-policy.json",
            ".agents/rules/rules.md",
            ".agents/skills/review-code/SKILL.md",
            "AGENTS.md",
        ],
    }
    _write(
        repo_root / ".agents/review-criteria-policy.json",
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
    )
    _run("git", "add", ".", cwd=repo_root)
    _run("git", "commit", "-m", "fixture", cwd=repo_root)
    divergent_head = _run("git", "rev-parse", "HEAD", cwd=repo_root)
    _run(
        "git",
        "update-ref",
        "refs/remotes/origin/develop",
        divergent_head,
        cwd=repo_root,
    )
    _run("git", "remote", "add", "origin", str(remote_root), cwd=repo_root)
    _run(
        "git",
        "push",
        "origin",
        "HEAD:refs/heads/feat/527",
        cwd=repo_root,
    )
    _write(repo_root / "current-head.txt", "current\n")
    _run("git", "add", "current-head.txt", cwd=repo_root)
    _run("git", "commit", "-m", "current head", cwd=repo_root)
    return _run("git", "rev-parse", "HEAD", cwd=repo_root), divergent_head


def _set_remote_head(repo_root: Path, head: str | None) -> None:
    if head is None:
        remote_root = _run("git", "remote", "get-url", "origin", cwd=repo_root)
        _run(
            "git",
            "-C",
            remote_root,
            "update-ref",
            "-d",
            "refs/heads/feat/527",
            cwd=repo_root,
        )
        return
    _run(
        "git",
        "push",
        "--force",
        "origin",
        f"{head}:refs/heads/feat/527",
        cwd=repo_root,
    )


def _review_binding(repo_root: Path, head: str) -> tuple[str, str]:
    try:
        base_sha = _run(
            "git",
            "merge-base",
            "origin/develop",
            head,
            cwd=repo_root,
        )
    except RuntimeError:
        return head, hashlib.sha256(b"").hexdigest()
    diff = subprocess.run(
        [
            "git",
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            f"{base_sha}...{head}",
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
    ).stdout
    return base_sha, hashlib.sha256(diff).hexdigest()


def _receipt(manifest: JsonObject, head: str, repo_root: Path) -> JsonObject:
    base_sha, diff_sha256 = _review_binding(repo_root, head)
    rows: list[JsonValue] = [
        {
            "category": category,
            "disposition": "reverified",
            "impact_reason": "exact HEAD checked",
            "evidence_paths": [".agents/rules/rules.md"],
            "ambiguous": False,
        }
        for category in CATEGORY_IDS
    ]
    findings: list[JsonValue] = []
    notes: list[JsonValue] = []
    criteria_digest = str(manifest["criteria_digest"])
    return {
        "schema_version": 1,
        "mode": "full",
        "head_sha": head,
        "base_sha": base_sha,
        "diff_sha256": diff_sha256,
        "issue_number": ISSUE_NUMBER,
        "criteria_digest": criteria_digest,
        "matrix_digest": compute_matrix_digest(rows),
        "result_digest": compute_result_digest(
            "PASS",
            findings,
            notes,
            head_sha=head,
            criteria_digest=criteria_digest,
            reviewer=REVIEWER,
        ),
        "owner": OWNER,
        "implementer": IMPLEMENTER,
        "reviewer": REVIEWER,
        "verdict": "PASS",
        "rows": rows,
        "findings": findings,
        "notes": notes,
        "blocker_count": 0,
    }


def _block_receipt(manifest: JsonObject, head: str, repo_root: Path) -> JsonObject:
    base_sha, diff_sha256 = _review_binding(repo_root, head)
    rows: list[JsonValue] = [
        {
            "category": category,
            "disposition": "reverified",
            "impact_reason": "exact HEAD checked",
            "evidence_paths": [".agents/rules/rules.md"],
            "ambiguous": False,
        }
        for category in CATEGORY_IDS
    ]
    findings: list[JsonValue] = [
        {
            "stable_key": "phase5-block",
            "root_cause_key": "phase5-block-root",
            "severity": "blocker",
            "summary": "exact-head blocker",
            "observation": "current HEAD violates the acceptance contract",
            "expected": "acceptance contract is satisfied",
            "actual": "acceptance contract is not satisfied",
            "acceptance_or_merge_impact": "merge must remain blocked",
            "impact": "publishing this receipt would approve a known defect",
            "reproduction": {
                "command": "uv run python reproduce.py",
                "head_sha": head,
                "exit_code": 1,
                "output_digest": "a" * 64,
            },
        }
    ]
    notes: list[JsonValue] = []
    criteria_digest = str(manifest["criteria_digest"])
    return {
        "schema_version": 1,
        "mode": "full",
        "head_sha": head,
        "base_sha": base_sha,
        "diff_sha256": diff_sha256,
        "issue_number": ISSUE_NUMBER,
        "criteria_digest": criteria_digest,
        "matrix_digest": compute_matrix_digest(rows),
        "result_digest": compute_result_digest(
            "BLOCK",
            findings,
            notes,
            head_sha=head,
            criteria_digest=criteria_digest,
            reviewer=REVIEWER,
        ),
        "owner": OWNER,
        "implementer": IMPLEMENTER,
        "reviewer": REVIEWER,
        "verdict": "BLOCK",
        "rows": rows,
        "findings": findings,
        "notes": notes,
        "blocker_count": 1,
    }


def _base_state(repo_root: Path, head: str) -> JsonObject:
    manifest = build_criteria_manifest(repo_root, ISSUE_NUMBER, ISSUE_BODY)
    return {
        "issue_number": ISSUE_NUMBER,
        "worktree": str(repo_root),
        "review_fast_path": {
            "schema_version": 1,
            "mode": "exact-head-receipt",
        },
        "owner": OWNER,
        "implementer": IMPLEMENTER,
        "commit_done": head,
        "final_review_delegate": {
            "head_sha": head,
            "criteria_digest": manifest["criteria_digest"],
            "reviewer": REVIEWER,
        },
        "final_local_review": {
            "manifest": manifest,
            "receipt": _receipt(manifest, head, repo_root),
        },
        "publication": {"state": "pending", "head_sha": head},
    }


def _write_state(repo_root: Path, state: Mapping[str, JsonValue]) -> Path:
    path = repo_root / ".process-state.json"
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _resolve(
    repo_root: Path,
    state: JsonObject,
    *,
    pr_candidates: list[JsonObject] | None = None,
) -> JsonObject:
    state_path = _write_state(repo_root, state)
    return resolve_phase5_resume(
        repo_root=repo_root,
        process_state_path=state_path,
        live_issue_body=ISSUE_BODY,
        pr_discovery=lambda _root, _branch, _head: (
            "E5presso/spakky-framework",
            list(pr_candidates or []),
        ),
    )


def _expect_error(action: Callable[[], object], expected_text: str) -> None:
    try:
        action()
    except Phase5ResumeError as error:
        assert expected_text in str(error), str(error)
    else:
        raise AssertionError(f"expected Phase5ResumeError containing {expected_text!r}")


def _push_checkpoint(state: JsonObject, head: str) -> None:
    state["push_done"] = "refs/heads/feat/527"
    state["push_head"] = head


def _pr(state: JsonObject, head: str) -> None:
    state["pr_opened"] = {
        "number": 99,
        "repo": "E5presso/spakky-framework",
        "url": "https://github.com/E5presso/spakky-framework/pull/99",
        "head_sha": head,
    }


def _published(head: str) -> JsonObject:
    return {
        "state": "published",
        "head_sha": head,
        "comment_id": 101,
        "comment_url": "https://github.com/example/comment/101",
        "comment_creator": "publisher",
        "label_verified": True,
        "status_id": 202,
        "status_creator": "publisher",
        "status_reused": False,
    }


def _pr_candidate(
    head: str,
    *,
    number: int = 99,
    repository: str = "E5presso/spakky-framework",
    branch: str = "feat/527",
) -> JsonObject:
    return {
        "number": number,
        "html_url": f"https://github.com/E5presso/spakky-framework/pull/{number}",
        "state": "open",
        "head": {
            "sha": head,
            "ref": branch,
            "repo": {"full_name": repository},
        },
        "base": {"repo": {"full_name": repository}},
    }


def _check_pr_adoption_selector(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    repository = "E5presso/spakky-framework"
    branch = "feat/527"
    assert (
        select_existing_pr(
            [],
            repository=repository,
            branch=branch,
            head=head,
        )
        is None
    )
    candidate = _pr_candidate(head)
    selected = select_existing_pr(
        [candidate],
        repository=repository,
        branch=branch,
        head=head,
    )
    assert selected == {
        "number": 99,
        "url": "https://github.com/E5presso/spakky-framework/pull/99",
        "repo": repository,
        "head_sha": head,
    }

    _set_remote_head(repo_root, head)
    adopted = _resolve(repo_root, deepcopy(base), pr_candidates=[candidate])
    assert adopted["mode"] == "resume-push-or-create-pr"
    assert adopted["next_action"] == (
        "record-push-checkpoint-then-adopt-existing-pr-converge-metadata-"
        "record-pr-checkpoint"
    )
    resolution = adopted["pr_resolution"]
    assert isinstance(resolution, dict)
    assert resolution["action"] == "adopt"
    assert resolution["gh_pr_create_allowed"] is False
    assert resolution["metadata_convergence_required"] is True

    second = _pr_candidate(head, number=100)
    _expect_error(
        lambda: select_existing_pr(
            [candidate, second],
            repository=repository,
            branch=branch,
            head=head,
        ),
        "multiple OPEN",
    )
    _expect_error(
        lambda: select_existing_pr(
            [_pr_candidate(head, repository="fork/project")],
            repository=repository,
            branch=branch,
            head=head,
        ),
        "not a same-repo",
    )
    _expect_error(
        lambda: select_existing_pr(
            [_pr_candidate("e" * 40)],
            repository=repository,
            branch=branch,
            head=head,
        ),
        "differs from exact current HEAD",
    )
    _expect_error(
        lambda: select_existing_pr(
            [_pr_candidate(head, branch="feat/other")],
            repository=repository,
            branch=branch,
            head=head,
        ),
        "branch differs",
    )


def _check_fresh_route(repo_root: Path, head: str) -> None:
    _set_remote_head(repo_root, None)
    state: JsonObject = {
        "issue_number": ISSUE_NUMBER,
        "worktree": str(repo_root),
        "review_fast_path": {
            "schema_version": 1,
            "mode": "exact-head-receipt",
        },
    }
    result = _resolve(repo_root, state)
    assert result["mode"] == "fresh-final-review"
    assert result["head_sha"] == head
    assert result["build_full_required"] is True
    assert result["next_action"] == "record-current-head-then-run-final-review"


def _check_receipt_resume_routes(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, None)
    no_push = _resolve(repo_root, deepcopy(base))
    assert no_push["mode"] == "resume-push-or-create-pr"
    assert no_push["push_checkpoint_present"] is False
    assert no_push["next_action"] == (
        "push-readback-record-checkpoint-then-create-or-adopt-pr"
    )
    assert no_push["build_full_required"] is False

    pushed = deepcopy(base)
    _push_checkpoint(pushed, head)
    _set_remote_head(repo_root, head)
    pushed_result = _resolve(repo_root, pushed)
    assert pushed_result["mode"] == "resume-push-or-create-pr"
    assert pushed_result["push_checkpoint_present"] is True
    assert pushed_result["next_action"] == (
        "create-pr-converge-metadata-record-pr-checkpoint"
    )
    assert pushed_result["pr_resolution"] == {
        "action": "create",
        "repository": "E5presso/spakky-framework",
        "branch": "feat/527",
        "head_sha": head,
        "gh_pr_create_allowed": True,
        "metadata_convergence_required": True,
    }
    assert pushed_result["build_full_required"] is False

    remote_only = _resolve(repo_root, deepcopy(base))
    assert remote_only["remote_exact"] is True
    assert remote_only["push_checkpoint_present"] is False
    assert remote_only["next_action"] == (
        "record-push-checkpoint-then-create-pr-converge-metadata-record-pr-checkpoint"
    )
    assert remote_only["build_full_required"] is False


def _check_pushurl_live_readback(
    repo_root: Path,
    push_remote: Path,
    head: str,
    base: JsonObject,
) -> None:
    _run("git", "init", "--bare", str(push_remote), cwd=repo_root.parent)
    _set_remote_head(repo_root, None)
    _run(
        "git",
        "push",
        str(push_remote),
        f"{head}:refs/heads/feat/527",
        cwd=repo_root,
    )
    _run(
        "git",
        "config",
        "--replace-all",
        "remote.origin.pushurl",
        str(push_remote),
        cwd=repo_root,
    )
    result = _resolve(repo_root, deepcopy(base))
    assert result["remote_exact"] is True
    resolution = result["pr_resolution"]
    assert isinstance(resolution, dict)
    assert resolution["action"] == "create"

    fetch_remote = _run("git", "remote", "get-url", "origin", cwd=repo_root)
    _run(
        "git",
        "config",
        "--add",
        "remote.origin.pushurl",
        fetch_remote,
        cwd=repo_root,
    )
    _expect_error(
        lambda: _resolve(repo_root, deepcopy(base)),
        "push endpoints disagree",
    )
    _run(
        "git",
        "config",
        "--unset-all",
        "remote.origin.pushurl",
        cwd=repo_root,
    )


def _check_invalid_receipt_after_push_fails(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, head)
    invalid = deepcopy(base)
    final_review = invalid["final_local_review"]
    assert isinstance(final_review, dict)
    receipt = final_review["receipt"]
    assert isinstance(receipt, dict)
    receipt["criteria_digest"] = "0" * 64
    _push_checkpoint(invalid, head)
    _expect_error(
        lambda: _resolve(repo_root, invalid),
        "without a publishable exact-head receipt",
    )

    remote_invalid = deepcopy(invalid)
    remote_invalid.pop("push_done")
    remote_invalid.pop("push_head")
    _expect_error(
        lambda: _resolve(repo_root, remote_invalid),
        "without a publishable exact-head receipt",
    )


def _check_block_resume(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    blocked = deepcopy(base)
    final_review = blocked["final_local_review"]
    assert isinstance(final_review, dict)
    manifest = final_review["manifest"]
    assert isinstance(manifest, dict)
    final_review["receipt"] = _block_receipt(manifest, head, repo_root)
    blocked["publication"] = {
        "state": "incomplete",
        "head_sha": head,
        "error": "final review BLOCK",
    }

    _set_remote_head(repo_root, None)
    result = _resolve(repo_root, blocked)
    assert result["mode"] == "resume-phase4-after-block"
    assert result["next_action"] == ("return-to-phase4-fix-commit-new-full-review")
    assert result["build_full_required"] is False

    _set_remote_head(repo_root, head)
    _expect_error(
        lambda: _resolve(repo_root, blocked),
        "BLOCK receipt cannot coexist with push",
    )


def _old_block_state(
    repo_root: Path,
    base: JsonObject,
    old_head: str,
) -> JsonObject:
    state = deepcopy(base)
    state["commit_done"] = old_head
    final_review = state["final_local_review"]
    assert isinstance(final_review, dict)
    manifest = final_review["manifest"]
    assert isinstance(manifest, dict)
    final_review["receipt"] = _block_receipt(manifest, old_head, repo_root)
    delegate = state["final_review_delegate"]
    assert isinstance(delegate, dict)
    delegate["head_sha"] = old_head
    state["publication"] = {
        "state": "incomplete",
        "head_sha": old_head,
        "error": "final review BLOCK",
    }
    return state


def _check_advanced_head_after_block(
    repo_root: Path,
    head: str,
    old_head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, None)
    state = _old_block_state(repo_root, base, old_head)
    state_path = _write_state(repo_root, state)
    before = state_path.read_bytes()
    result = resolve_phase5_resume(
        repo_root=repo_root,
        process_state_path=state_path,
        live_issue_body=ISSUE_BODY,
    )
    assert result["mode"] == "resume-new-head-final-review"
    assert result["next_action"] == (
        "clear-old-head-evidence-record-current-head-then-run-final-review"
    )
    transition = result["state_transition"]
    assert isinstance(transition, dict)
    assert transition["expected_old_commit_done"] == old_head
    assert transition["set"] == {"commit_done": head}
    assert transition["delete"] == [
        "final_local_review",
        "final_review_delegate",
        "publication",
        "final_review_inputs",
        "push_done",
        "push_head",
        "pr_opened",
    ]
    assert state_path.read_bytes() == before

    tree = _run("git", "rev-parse", "HEAD^{tree}", cwd=repo_root)
    unrelated = _run(
        "git",
        "commit-tree",
        tree,
        "-m",
        "unrelated block head",
        cwd=repo_root,
    )
    nonancestor = _old_block_state(repo_root, base, unrelated)
    _expect_error(
        lambda: _resolve(repo_root, nonancestor),
        "not backed by the prior exact-head BLOCK receipt",
    )


def _state_with_surviving_inputs(
    repo_root: Path,
    head: str,
    base: JsonObject,
    *,
    keep_receipt: bool = False,
    verdict: str = "PASS",
) -> tuple[JsonObject, Path]:
    state = deepcopy(base)
    if not keep_receipt:
        state.pop("final_local_review")
        state.pop("publication")
    directory = Path(mkdtemp(prefix=f"spakky-final-review-{ISSUE_NUMBER}.")).resolve(
        strict=True
    )
    manifest = build_criteria_manifest(repo_root, ISSUE_NUMBER, ISSUE_BODY)
    manifest_path = directory / "criteria-manifest.json"
    issue_body_path = directory / "issue-body.md"
    diff_path = directory / "committed.diff"
    _write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write(issue_body_path, ISSUE_BODY)
    base_sha = _run("git", "rev-parse", "HEAD^", cwd=repo_root)
    diff = subprocess.run(
        [
            "git",
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            f"{base_sha}...{head}",
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
    ).stdout
    diff_path.write_bytes(diff)
    state["final_review_inputs"] = {
        "temp_dir": str(directory),
        "manifest_path": str(manifest_path),
        "issue_body_path": str(issue_body_path),
        "diff_path": str(diff_path),
        "head_sha": head,
        "criteria_digest": manifest["criteria_digest"],
        "base_sha": base_sha,
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
    }
    receipt = (
        _receipt(manifest, head, repo_root)
        if verdict == "PASS"
        else _block_receipt(manifest, head, repo_root)
    )
    _write(
        directory / "review-result.json",
        json.dumps(
            {
                "reviewer": REVIEWER,
                "head_sha": head,
                "base_sha": base_sha,
                "diff_sha256": hashlib.sha256(diff).hexdigest(),
                "criteria_digest": manifest["criteria_digest"],
                "verdict": receipt["verdict"],
                "rows": receipt["rows"],
                "findings": receipt["findings"],
                "notes": receipt["notes"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    if keep_receipt:
        state["final_local_review"] = {
            "manifest": manifest,
            "receipt": receipt,
        }
        state["publication"] = (
            {"state": "pending", "head_sha": head}
            if verdict == "PASS"
            else {
                "state": "incomplete",
                "head_sha": head,
                "error": "final review BLOCK",
            }
        )
    return state, directory


def _check_surviving_inputs_resume(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    state, directory = _state_with_surviving_inputs(repo_root, head, base)
    try:
        _set_remote_head(repo_root, None)
        state_path = _write_state(repo_root, state)
        before = state_path.read_bytes()
        result = resolve_phase5_resume(
            repo_root=repo_root,
            process_state_path=state_path,
            live_issue_body=ISSUE_BODY,
        )
        assert result["mode"] == "resume-final-review-inputs"
        assert result["next_action"] == "rehydrate-final-review-inputs"
        assert result["build_full_required"] is True
        assert result["final_review_inputs"] == state["final_review_inputs"]
        assert state_path.read_bytes() == before
        assert directory.is_dir()
        assert (directory / "criteria-manifest.json").is_file()

        invalid = deepcopy(state)
        inputs = invalid["final_review_inputs"]
        assert isinstance(inputs, dict)
        inputs["diff_path"] = str(directory / "missing.diff")
        invalid_path = _write_state(repo_root, invalid)
        invalid_before = invalid_path.read_bytes()
        _expect_error(
            lambda: resolve_phase5_resume(
                repo_root=repo_root,
                process_state_path=invalid_path,
                live_issue_body=ISSUE_BODY,
            ),
            "preserve them for diagnosis",
        )
        assert invalid_path.read_bytes() == invalid_before
        assert directory.is_dir()
    finally:
        shutil.rmtree(directory)


def _check_post_build_cleanup_resume(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, None)
    for verdict, expected_mode, expected_after in (
        (
            "PASS",
            "resume-cleanup-final-review-inputs",
            "resume-push-or-create-pr",
        ),
        (
            "BLOCK",
            "resume-cleanup-blocked-review-inputs",
            "resume-phase4-after-block",
        ),
    ):
        state, directory = _state_with_surviving_inputs(
            repo_root,
            head,
            base,
            keep_receipt=True,
            verdict=verdict,
        )
        state_path = _write_state(repo_root, state)
        result = resolve_phase5_resume(
            repo_root=repo_root,
            process_state_path=state_path,
            live_issue_body=ISSUE_BODY,
        )
        assert result["mode"] == expected_mode
        transition = result["state_transition"]
        assert isinstance(transition, dict)
        assert transition["command"] == "review_receipt.py cleanup-inputs"
        assert transition["receipt_verdict"] == verdict
        consumed = cleanup_final_review_inputs(state_path, repo_root)
        assert consumed == {
            "head_sha": head,
            "verdict": verdict,
            "state": "consumed",
        }
        assert not directory.exists()
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert "final_review_inputs" not in persisted
        after = resolve_phase5_resume(
            repo_root=repo_root,
            process_state_path=state_path,
            live_issue_body=ISSUE_BODY,
            pr_discovery=lambda _root, _branch, _head: (
                "E5presso/spakky-framework",
                [],
            ),
        )
        assert after["mode"] == expected_after


def _check_push_endpoint_errors_redact_credentials(repo_root: Path) -> None:
    endpoint = "https://secret-token@example.invalid/private.git"
    failed = subprocess.CompletedProcess(
        args=["git"],
        returncode=128,
        stdout="",
        stderr=f"fatal: unable to access {endpoint}",
    )
    with patch("resolve_phase5_resume.subprocess.run", return_value=failed):
        try:
            _ls_remote_push_endpoint(
                repo_root,
                endpoint,
                "refs/heads/feat/527",
            )
        except Phase5ResumeError as error:
            message = str(error)
            assert "configured push endpoint" in message
            assert "secret-token" not in message
            assert endpoint not in message
        else:
            raise AssertionError(
                "failed credential-bearing endpoint unexpectedly passed"
            )


def _check_pr_publication_routes(
    repo_root: Path,
    head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, head)
    pending = deepcopy(base)
    _push_checkpoint(pending, head)
    _pr(pending, head)
    pending_result = _resolve(repo_root, pending)
    assert pending_result["mode"] == "resume-in-review-publication"
    assert pending_result["next_action"] == (
        "revalidate-live-pr-replay-in-review-then-publish"
    )
    required_effects = [
        "live-pr-identity-readback",
        "project-status-in-review",
        "receipt-publisher",
        "live-publication-readback",
    ]
    assert pending_result["required_effects"] == required_effects
    observed_effects: list[str] = []
    callbacks = {
        effect: (lambda current=effect: observed_effects.append(current))
        for effect in required_effects
    }
    raw_effects = pending_result["required_effects"]
    assert isinstance(raw_effects, list)
    parsed_effects: list[str] = []
    for effect in raw_effects:
        assert isinstance(effect, str)
        parsed_effects.append(effect)
        callbacks[effect]()
    assert parsed_effects == required_effects
    assert observed_effects == required_effects
    assert pending_result["build_full_required"] is False

    incomplete = deepcopy(pending)
    incomplete["publication"] = {
        "state": "incomplete",
        "head_sha": head,
        "error": "transient status failure",
    }
    incomplete_result = _resolve(repo_root, incomplete)
    assert incomplete_result["mode"] == "resume-in-review-publication"
    assert incomplete_result["build_full_required"] is False

    published = deepcopy(pending)
    published["publication"] = _published(head)
    published_result = _resolve(repo_root, published)
    assert published_result["mode"] == "resume-in-review-publication"
    assert published_result["next_action"] == (
        "revalidate-live-pr-replay-in-review-then-publish"
    )
    assert published_result["required_effects"] == required_effects
    assert published_result["build_full_required"] is False

    merged = deepcopy(published)
    merged["merged"] = "f" * 40
    merged_result = _resolve(repo_root, merged)
    assert merged_result["mode"] == "merged"
    assert merged_result["next_action"] == "none"
    assert merged_result["build_full_required"] is False


def _check_inconsistent_state_fails(
    repo_root: Path,
    head: str,
    divergent_head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, head)
    pr_without_push = deepcopy(base)
    _pr(pr_without_push, head)
    recovered_pr = _resolve(repo_root, pr_without_push)
    assert recovered_pr["mode"] == "resume-in-review-publication"
    assert recovered_pr["next_action"] == (
        "record-push-checkpoint-then-revalidate-live-pr-replay-in-review-then-publish"
    )

    partial_push = deepcopy(base)
    partial_push["push_head"] = head
    _expect_error(
        lambda: _resolve(repo_root, partial_push),
        "same checkpoint",
    )

    wrong_ref = deepcopy(base)
    _push_checkpoint(wrong_ref, head)
    wrong_ref["push_done"] = "refs/heads/another-branch"
    _expect_error(
        lambda: _resolve(repo_root, wrong_ref),
        "differs from the current branch ref",
    )

    contradictory_remote = deepcopy(base)
    _push_checkpoint(contradictory_remote, head)
    _set_remote_head(repo_root, divergent_head)
    _expect_error(
        lambda: _resolve(repo_root, contradictory_remote),
        "live remote head contradicts the push checkpoint",
    )

    published_without_pr = deepcopy(base)
    published_without_pr["publication"] = _published(head)
    _set_remote_head(repo_root, head)
    _expect_error(
        lambda: _resolve(repo_root, published_without_pr),
        "before PR identity",
    )


def _check_legacy_routes(repo_root: Path, head: str) -> None:
    legacy: JsonObject = {
        "issue_number": ISSUE_NUMBER,
        "worktree": str(repo_root),
    }
    process_result = _resolve(repo_root, deepcopy(legacy))
    assert process_result["mode"] == "legacy-resume-process"
    assert process_result["receipt_valid"] is False

    dirty_path = repo_root / "legacy-uncommitted.txt"
    _write(dirty_path, "legacy work in progress\n")
    try:
        dirty_result = _resolve(repo_root, deepcopy(legacy))
        assert dirty_result["mode"] == "legacy-resume-process"
    finally:
        dirty_path.unlink()

    legacy_pr = deepcopy(legacy)
    legacy_pr["pr_opened"] = {
        "number": 77,
        "url": "https://github.com/E5presso/spakky-framework/pull/77",
    }
    monitor_result = _resolve(repo_root, legacy_pr)
    assert monitor_result["mode"] == "legacy-resume-monitor"
    assert monitor_result["next_action"] == "legacy-monitor-pr"

    legacy_merged = deepcopy(legacy)
    legacy_merged["merged"] = "f" * 40
    merged_result = _resolve(repo_root, legacy_merged)
    assert merged_result["mode"] == "merged"

    forged = deepcopy(legacy)
    forged["review_fast_path"] = {
        "schema_version": 1,
        "mode": "made-up-fast-path",
    }
    _expect_error(
        lambda: _resolve(repo_root, forged),
        "marker is unsupported",
    )

    assert head == _run("git", "rev-parse", "HEAD", cwd=repo_root)


def _check_cli_contract(
    repo_root: Path,
    issue_body_path: Path,
    head: str,
    divergent_head: str,
    base: JsonObject,
) -> None:
    _set_remote_head(repo_root, None)
    state = deepcopy(base)
    state_path = _write_state(repo_root, state)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIRECTORY / "resolve_phase5_resume.py"),
            "--repo-root",
            str(repo_root),
            "--process-state",
            str(state_path),
            "--issue-body-file",
            str(issue_body_path),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["mode"] == "resume-push-or-create-pr"
    assert result["build_full_required"] is False
    assert "build-full" not in result["next_action"]

    caller_forgery = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIRECTORY / "resolve_phase5_resume.py"),
            "--repo-root",
            str(repo_root),
            "--process-state",
            str(state_path),
            "--issue-body-file",
            str(issue_body_path),
            "--remote-head",
            head,
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert caller_forgery.returncode == 2
    assert caller_forgery.stdout == ""
    assert "unrecognized arguments: --remote-head" in caller_forgery.stderr

    _push_checkpoint(state, head)
    state_path = _write_state(repo_root, state)
    _set_remote_head(repo_root, divergent_head)
    stale_remote = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIRECTORY / "resolve_phase5_resume.py"),
            "--repo-root",
            str(repo_root),
            "--process-state",
            str(state_path),
            "--issue-body-file",
            str(issue_body_path),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stale_remote.returncode == 2
    assert stale_remote.stdout == ""
    assert "live remote head contradicts the push checkpoint" in stale_remote.stderr


def main() -> int:
    _isolate_fixture_git_environment()
    with TemporaryDirectory(prefix="phase5-resume-contract-") as temporary:
        directory = Path(temporary)
        repo_root = directory / "repo"
        remote_root = directory / "remote.git"
        push_remote = directory / "push-remote.git"
        head, divergent_head = _initialize_repository(repo_root, remote_root)
        repo_root = repo_root.resolve(strict=True)
        issue_body_path = directory / "issue-body.md"
        _write(issue_body_path, ISSUE_BODY)
        base = _base_state(repo_root, head)

        checks = [
            lambda: _check_fresh_route(repo_root, head),
            lambda: _check_receipt_resume_routes(repo_root, head, base),
            lambda: _check_pushurl_live_readback(
                repo_root,
                push_remote,
                head,
                base,
            ),
            lambda: _check_pr_adoption_selector(repo_root, head, base),
            lambda: _check_invalid_receipt_after_push_fails(repo_root, head, base),
            lambda: _check_block_resume(repo_root, head, base),
            lambda: _check_advanced_head_after_block(
                repo_root,
                head,
                divergent_head,
                base,
            ),
            lambda: _check_surviving_inputs_resume(repo_root, head, base),
            lambda: _check_post_build_cleanup_resume(repo_root, head, base),
            lambda: _check_push_endpoint_errors_redact_credentials(repo_root),
            lambda: _check_pr_publication_routes(repo_root, head, base),
            lambda: _check_inconsistent_state_fails(
                repo_root,
                head,
                divergent_head,
                base,
            ),
            lambda: _check_legacy_routes(repo_root, head),
            lambda: _check_cli_contract(
                repo_root,
                issue_body_path,
                head,
                divergent_head,
                base,
            ),
        ]
        for check in checks:
            check()
    print(f"phase5-resume-contract: {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
