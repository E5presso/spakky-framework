"""Function-based contract checks for exact-head review receipts."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIRECTORY))
from review_receipt import (  # noqa: E402 - contract imports sibling script
    _remote_heads_for_endpoint,
    CATEGORY_IDS,
    JsonObject,
    JsonValue,
    ReviewReceiptError,
    build_criteria_manifest,
    compute_matrix_digest,
    compute_result_digest,
    normalize_issue_body,
    validate_delta_receipt,
    validate_full_receipt,
    validate_process_state_full_receipt,
    validate_publishable_full_receipt,
)


HEAD = "a" * 40
DESCENDANT_HEAD = "b" * 40
BASE_SHA = "0" * 40
DIFF_SHA256 = "e" * 64
ISSUE_NUMBER = 527
ISSUE_BODY = "# Receipt\r\n\r\nCafé  \r\n"


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


def _write_policy(repo_root: Path, sources: list[str] | None = None) -> None:
    policy_path = repo_root / ".agents/review-criteria-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "categories": list(CATEGORY_IDS),
                "sources": sources
                or [
                    ".agents/review-criteria-policy.json",
                    ".agents/rules.md",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / ".agents/rules.md").write_text("# Rules\n", encoding="utf-8")


def _manifest(repo_root: Path) -> JsonObject:
    return build_criteria_manifest(repo_root, ISSUE_NUMBER, ISSUE_BODY)


def _rows(*, inherited: set[str] | None = None) -> list[JsonValue]:
    inherited = inherited or set()
    result: list[JsonValue] = []
    for category in CATEGORY_IDS:
        if category in inherited:
            result.append(
                {
                    "category": category,
                    "disposition": "inherited",
                    "unaffected_reason": "frozen criterion is unaffected",
                    "evidence_paths": [".agents/rules.md"],
                    "ambiguous": False,
                }
            )
            continue
        result.append(
            {
                "category": category,
                "disposition": "reverified",
                "impact_reason": "current HEAD inspected",
                "evidence_paths": ["changed.py"],
                "ambiguous": False,
            }
        )
    return result


def _receipt(
    manifest: JsonObject,
    *,
    head: str = HEAD,
    verdict: str = "PASS",
    findings: list[JsonValue] | None = None,
    notes: list[JsonValue] | None = None,
) -> JsonObject:
    rows = _rows()
    receipt_findings = findings or []
    receipt_notes = notes or []
    blocker_count = sum(_severity(finding) == "blocker" for finding in receipt_findings)
    return {
        "schema_version": 1,
        "mode": "full",
        "head_sha": head,
        "base_sha": BASE_SHA,
        "diff_sha256": DIFF_SHA256,
        "issue_number": ISSUE_NUMBER,
        "criteria_digest": manifest["criteria_digest"],
        "matrix_digest": compute_matrix_digest(rows),
        "result_digest": compute_result_digest(
            verdict,
            receipt_findings,
            receipt_notes,
            head_sha=head,
            criteria_digest=str(manifest["criteria_digest"]),
            reviewer="independent-reviewer",
        ),
        "owner": "owner",
        "implementer": "implementer",
        "reviewer": "independent-reviewer",
        "verdict": verdict,
        "rows": rows,
        "findings": receipt_findings,
        "notes": receipt_notes,
        "blocker_count": blocker_count,
    }


def _delegate(
    manifest: JsonObject,
    *,
    head: str = HEAD,
    reviewer: str = "independent-reviewer",
) -> JsonObject:
    return {
        "head_sha": head,
        "criteria_digest": manifest["criteria_digest"],
        "reviewer": reviewer,
    }


def _severity(value: JsonValue) -> JsonValue:
    if not isinstance(value, dict):
        raise AssertionError("finding fixture must be an object")
    return value.get("severity")


def _mutable_rows(receipt: JsonObject) -> list[JsonValue]:
    rows = receipt.get("rows")
    if not isinstance(rows, list):
        raise AssertionError("receipt fixture rows must be an array")
    return rows


def _mutable_row(rows: list[JsonValue], index: int) -> JsonObject:
    row = rows[index]
    if not isinstance(row, dict):
        raise AssertionError("receipt fixture row must be an object")
    return row


def _expect_error(action: Callable[[], JsonValue | None], expected: str) -> None:
    try:
        action()
    except ReviewReceiptError as error:
        assert expected in str(error), str(error)
        return
    raise AssertionError(f"expected ReviewReceiptError containing {expected!r}")


def test_issue_normalization_preserves_semantics_expect_canonical_text() -> None:
    """NFC, LF, horizontal whitespace, and terminal newline are canonical."""

    decomposed = "# T\r\nCafe\u0301 \t\r\n\r\n"
    assert normalize_issue_body(decomposed) == "# T\nCafé\n"


def test_full_receipt_valid_expect_publishable() -> None:
    """A distinct reviewer and 14 reverified rows form a publishable receipt."""

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root)
        manifest = _manifest(repo_root)
        receipt = _receipt(manifest)
        validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER)
        validate_publishable_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER)


def test_full_receipt_stale_and_incomplete_expect_rejected() -> None:
    """Stale heads, missing categories, and duplicate categories fail closed."""

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root)
        manifest = _manifest(repo_root)
        receipt = _receipt(manifest)
        _expect_error(
            lambda: validate_full_receipt(
                receipt,
                manifest,
                DESCENDANT_HEAD,
                ISSUE_NUMBER,
            ),
            "head SHA mismatch",
        )
        incomplete = deepcopy(receipt)
        incomplete_rows = _mutable_rows(incomplete)[:-1]
        incomplete["rows"] = incomplete_rows
        incomplete["matrix_digest"] = compute_matrix_digest(incomplete_rows)
        _expect_error(
            lambda: validate_full_receipt(incomplete, manifest, HEAD, ISSUE_NUMBER),
            "exactly 14",
        )
        duplicate = deepcopy(receipt)
        duplicate_rows = _mutable_rows(duplicate)
        _mutable_row(duplicate_rows, 13)["category"] = "C13"
        duplicate["matrix_digest"] = compute_matrix_digest(duplicate_rows)
        _expect_error(
            lambda: validate_full_receipt(duplicate, manifest, HEAD, ISSUE_NUMBER),
            "C01-C14 exactly once in canonical order",
        )
        reordered = deepcopy(receipt)
        reordered_rows = _mutable_rows(reordered)
        reordered_rows[0], reordered_rows[1] = reordered_rows[1], reordered_rows[0]
        reordered["matrix_digest"] = compute_matrix_digest(reordered_rows)
        _expect_error(
            lambda: validate_full_receipt(reordered, manifest, HEAD, ISSUE_NUMBER),
            "canonical order",
        )


def test_identity_and_live_issue_drift_expect_rejected() -> None:
    """Self-review and a changed live issue cannot reuse the frozen receipt."""

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root)
        manifest = _manifest(repo_root)
        receipt = _receipt(manifest)
        receipt["reviewer"] = "OWNER"
        _expect_error(
            lambda: validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER),
            "reviewer must differ",
        )
        receipt = _receipt(manifest)
        receipt["reviewer"] = "owner "
        _expect_error(
            lambda: validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER),
            "trimmed NFC identity token",
        )
        receipt = _receipt(manifest)
        receipt["reviewer"] = "owner\u200b"
        _expect_error(
            lambda: validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER),
            "using ASCII",
        )
        receipt = _receipt(manifest)
        state: JsonObject = {
            "commit_done": HEAD,
            "owner": "owner",
            "implementer": "implementer",
            "final_review_delegate": _delegate(manifest),
            "final_local_review": {"manifest": manifest, "receipt": receipt},
        }
        _expect_error(
            lambda: validate_process_state_full_receipt(
                state,
                repo_root,
                ISSUE_BODY + "changed\n",
                HEAD,
                ISSUE_NUMBER,
            ),
            "differs from live criteria",
        )
        state["final_review_delegate"] = _delegate(
            manifest,
            reviewer="different-reviewer",
        )
        _expect_error(
            lambda: validate_process_state_full_receipt(
                state,
                repo_root,
                ISSUE_BODY,
                HEAD,
                ISSUE_NUMBER,
            ),
            "delegate reviewer differs from receipt",
        )


def test_blocker_evidence_and_key_uniqueness_expect_enforced() -> None:
    """Blockers need executable evidence and all finding/note keys are unique."""

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root)
        manifest = _manifest(repo_root)
        incomplete_blocker: JsonValue = {
            "stable_key": "blocker-1",
            "root_cause_key": "root-1",
            "severity": "blocker",
            "summary": "broken",
        }
        receipt = _receipt(
            manifest,
            verdict="BLOCK",
            findings=[incomplete_blocker],
        )
        _expect_error(
            lambda: validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER),
            "observation",
        )
        valid_blocker: JsonValue = {
            "stable_key": "blocker-2",
            "root_cause_key": "root-2",
            "severity": "blocker",
            "summary": "broken at exact head",
            "observation": "contract command fails",
            "reproduction": {
                "command": "uv run python check_contract.py",
                "head_sha": HEAD,
                "exit_code": 1,
                "output_digest": "c" * 64,
            },
            "expected": "exit 0",
            "actual": "exit 1",
            "acceptance_or_merge_impact": "SC-001 fails",
            "impact": "invalid receipt could be published",
        }
        receipt = _receipt(
            manifest,
            verdict="BLOCK",
            findings=[valid_blocker],
        )
        validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER)
        wrong_head_blocker = deepcopy(valid_blocker)
        assert isinstance(wrong_head_blocker, dict)
        reproduction = wrong_head_blocker.get("reproduction")
        assert isinstance(reproduction, dict)
        reproduction["head_sha"] = DESCENDANT_HEAD
        receipt = _receipt(
            manifest,
            verdict="BLOCK",
            findings=[wrong_head_blocker],
        )
        _expect_error(
            lambda: validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER),
            "reproduction head SHA mismatch",
        )
        warning: JsonValue = {
            "stable_key": "duplicate",
            "root_cause_key": "duplicate-root",
            "severity": "warning",
            "summary": "warning evidence",
        }
        note: JsonValue = {
            "stable_key": "duplicate",
            "root_cause_key": "note-root",
            "text": "review note",
        }
        receipt = _receipt(manifest, findings=[warning], notes=[note])
        _expect_error(
            lambda: validate_full_receipt(receipt, manifest, HEAD, ISSUE_NUMBER),
            "stable keys must be unique",
        )


def test_delta_partition_expect_validator_only() -> None:
    """A proven descendant partition validates but remains non-publishable."""

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root)
        manifest = _manifest(repo_root)
        prior = _receipt(manifest)
        delta = _receipt(manifest, head=DESCENDANT_HEAD)
        delta["mode"] = "delta"
        delta["prior_head_sha"] = HEAD
        delta["rows"] = _rows(inherited=set(CATEGORY_IDS[1:]))
        delta_rows = _mutable_rows(delta)
        delta["matrix_digest"] = compute_matrix_digest(delta_rows)
        validate_delta_receipt(delta, prior, manifest, lambda base, head: True)
        _expect_error(
            lambda: validate_publishable_full_receipt(
                delta,
                manifest,
                DESCENDANT_HEAD,
                ISSUE_NUMBER,
            ),
            "mode must be 'full'",
        )
        _expect_error(
            lambda: validate_delta_receipt(
                delta,
                prior,
                manifest,
                lambda base, head: False,
            ),
            "not an ancestor",
        )
        ambiguous = deepcopy(delta)
        ambiguous_rows = _mutable_rows(ambiguous)
        _mutable_row(ambiguous_rows, 1)["ambiguous"] = True
        ambiguous["matrix_digest"] = compute_matrix_digest(ambiguous_rows)
        _expect_error(
            lambda: validate_delta_receipt(
                ambiguous,
                prior,
                manifest,
                lambda base, head: True,
            ),
            "cannot be inherited",
        )


def test_policy_path_safety_expect_rejected() -> None:
    """Duplicate, traversal, and symlink criteria sources fail manifest freeze."""

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root, [".agents/rules.md", ".agents/rules.md"])
        _expect_error(lambda: _manifest(repo_root), "nonempty and unique")
        _write_policy(repo_root, ["../outside.md"])
        _expect_error(lambda: _manifest(repo_root), "repo-relative")
        target = repo_root / "real.md"
        target.write_text("real\n", encoding="utf-8")
        link = repo_root / ".agents/link.md"
        link.symlink_to(target)
        _write_policy(repo_root, [".agents/link.md"])
        _expect_error(lambda: _manifest(repo_root), "symlink")

    with TemporaryDirectory() as directory:
        repo_root = Path(directory)
        _write_policy(repo_root)
        (repo_root / "AGENTS.md").write_text("# review rules\n", encoding="utf-8")
        _expect_error(lambda: _manifest(repo_root), "omits required review sources")


def test_push_endpoint_error_expect_credentials_redacted() -> None:
    """Credential-bearing push URLs and remote stderr never enter diagnostics."""

    endpoint = "https://secret-token@example.invalid/private.git"
    failed = subprocess.CompletedProcess(
        args=["git"],
        returncode=128,
        stdout="",
        stderr=f"fatal: unable to access {endpoint}",
    )
    with TemporaryDirectory() as directory:
        with patch("review_receipt.subprocess.run", return_value=failed):
            try:
                _remote_heads_for_endpoint(Path(directory), endpoint)
            except ReviewReceiptError as error:
                message = str(error)
                assert "configured push endpoint" in message
                assert "secret-token" not in message
                assert endpoint not in message
            else:
                raise AssertionError(
                    "failed credential-bearing endpoint unexpectedly passed"
                )


def test_build_full_cli_clean_commit_expect_state_receipt() -> None:
    """The executable CLI freezes a clean commit and validates its stored state."""

    with (
        TemporaryDirectory() as directory,
        TemporaryDirectory(
            prefix=f"spakky-final-review-{ISSUE_NUMBER}."
        ) as input_directory,
    ):
        fixture_root = Path(directory)
        input_root = Path(input_directory).resolve()
        repo_root = fixture_root / "repo"
        repo_root.mkdir()
        _write_policy(repo_root)
        (repo_root / ".gitignore").write_text(
            ".process-state.json\n",
            encoding="utf-8",
        )
        for arguments in (
            ("init",),
            ("config", "user.name", "Receipt Contract"),
            ("config", "user.email", "receipt@example.invalid"),
            ("config", "core.hooksPath", "/dev/null"),
            ("add", "."),
            ("commit", "-m", "test: freeze receipt fixture"),
        ):
            completed = subprocess.run(
                ["git", "-C", str(repo_root), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
        base_sha = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        updated_base_ref = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "update-ref",
                "refs/remotes/origin/develop",
                base_sha,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert updated_base_ref.returncode == 0, updated_base_ref.stderr
        (repo_root / "change.txt").write_text("reviewed change\n", encoding="utf-8")
        for arguments in (
            ("add", "change.txt"),
            ("commit", "-m", "feat: add reviewed change"),
        ):
            completed = subprocess.run(
                ["git", "-C", str(repo_root), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        manifest = _manifest(repo_root)
        issue_path = input_root / "issue-body.md"
        issue_path.write_text(ISSUE_BODY, encoding="utf-8")
        manifest_path = input_root / "criteria-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        committed_diff = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--binary",
                "--no-ext-diff",
                "--no-textconv",
                f"{base_sha}...{head}",
            ],
            capture_output=True,
            check=True,
        ).stdout
        diff_sha256 = hashlib.sha256(committed_diff).hexdigest()
        diff_path = input_root / "committed.diff"
        diff_path.write_bytes(committed_diff)
        state_path = repo_root / ".process-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "issue_number": ISSUE_NUMBER,
                    "worktree": str(repo_root.resolve()),
                    "commit_done": head,
                    "owner": "owner",
                    "implementer": "implementer",
                    "final_review_delegate": {
                        "head_sha": head,
                        "criteria_digest": manifest["criteria_digest"],
                        "reviewer": "independent-reviewer",
                    },
                    "final_review_inputs": {
                        "temp_dir": str(input_root),
                        "manifest_path": str(manifest_path),
                        "issue_body_path": str(issue_path),
                        "diff_path": str(diff_path),
                        "head_sha": head,
                        "criteria_digest": manifest["criteria_digest"],
                        "base_sha": base_sha,
                        "diff_sha256": diff_sha256,
                    },
                }
            ),
            encoding="utf-8",
        )
        result_path = input_root / "review-result.json"
        result_path.write_text(
            json.dumps(
                {
                    "head_sha": head,
                    "base_sha": base_sha,
                    "diff_sha256": diff_sha256,
                    "criteria_digest": manifest["criteria_digest"],
                    "reviewer": "independent-reviewer",
                    "verdict": "PASS",
                    "rows": _rows(),
                    "findings": [],
                    "notes": [],
                }
            ),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(SCRIPT_DIRECTORY / "review_receipt.py"),
            "build-full",
            "--repo-root",
            str(repo_root),
            "--process-state",
            str(state_path),
            "--issue-number",
            str(ISSUE_NUMBER),
            "--issue-body-file",
            str(issue_path),
            "--review-result",
            str(result_path),
            "--head",
            head,
        ]
        resumed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIRECTORY / "review_receipt.py"),
                "resume-inputs",
                "--repo-root",
                str(repo_root),
                "--process-state",
                str(state_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert resumed.returncode == 0, resumed.stderr
        resumed_inputs = json.loads(resumed.stdout)
        assert resumed_inputs["temp_dir"] == str(input_root)
        assert resumed_inputs["head_sha"] == head
        assert resumed_inputs["base_sha"] == base_sha
        assert resumed_inputs["diff_sha256"] == diff_sha256
        process_state = json.loads(state_path.read_text(encoding="utf-8"))
        process_state["final_review_inputs"]["diff_path"] = str(
            input_root / "other.diff"
        )
        state_path.write_text(json.dumps(process_state), encoding="utf-8")
        invalid_resume = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIRECTORY / "review_receipt.py"),
                "resume-inputs",
                "--repo-root",
                str(repo_root),
                "--process-state",
                str(state_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert invalid_resume.returncode == 2
        assert "diff_path is not canonical" in invalid_resume.stderr
        process_state["final_review_inputs"]["diff_path"] = str(diff_path)
        diff_path.write_text("tampered diff\n", encoding="utf-8")
        state_path.write_text(json.dumps(process_state), encoding="utf-8")
        invalid_diff = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIRECTORY / "review_receipt.py"),
                "resume-inputs",
                "--repo-root",
                str(repo_root),
                "--process-state",
                str(state_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert invalid_diff.returncode == 2
        assert "committed diff differs from the exact Git diff" in invalid_diff.stderr
        diff_path.write_bytes(committed_diff)
        process_state["issue_number"] = str(ISSUE_NUMBER)
        state_path.write_text(json.dumps(process_state), encoding="utf-8")
        string_issue = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert string_issue.returncode == 2
        assert "process state.issue_number must be a nonnegative integer" in (
            string_issue.stderr
        )
        process_state["issue_number"] = ISSUE_NUMBER + 1
        state_path.write_text(json.dumps(process_state), encoding="utf-8")
        drifted = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert drifted.returncode == 2
        assert "process state issue number mismatch" in drifted.stderr, drifted.stderr
        process_state["issue_number"] = ISSUE_NUMBER
        state_path.write_text(json.dumps(process_state), encoding="utf-8")
        drifted_result = json.loads(result_path.read_text(encoding="utf-8"))
        drifted_result["head_sha"] = DESCENDANT_HEAD
        result_path.write_text(json.dumps(drifted_result), encoding="utf-8")
        drifted = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert drifted.returncode == 2
        assert "review result head SHA mismatch" in drifted.stderr
        assert "final_local_review" not in json.loads(
            state_path.read_text(encoding="utf-8")
        )
        drifted_result["head_sha"] = head
        drifted_result["criteria_digest"] = "d" * 64
        result_path.write_text(json.dumps(drifted_result), encoding="utf-8")
        drifted = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert drifted.returncode == 2
        assert "review result criteria digest mismatch" in drifted.stderr
        drifted_result["criteria_digest"] = manifest["criteria_digest"]
        drifted_result["reviewer"] = "implementer"
        result_path.write_text(json.dumps(drifted_result), encoding="utf-8")
        drifted = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert drifted.returncode == 2
        assert "review result reviewer differs from delegate" in drifted.stderr
        drifted_result["reviewer"] = "independent-reviewer"
        result_path.write_text(json.dumps(drifted_result), encoding="utf-8")
        built = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert built.returncode == 0, built.stderr
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["publication"] == {"head_sha": head, "state": "pending"}
        assert state["final_local_review"]["receipt"]["head_sha"] == head
        assert state["final_local_review"]["receipt"]["base_sha"] == base_sha
        assert state["final_local_review"]["receipt"]["diff_sha256"] == diff_sha256
        validated = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIRECTORY / "review_receipt.py"),
                "validate-full",
                "--repo-root",
                str(repo_root),
                "--process-state",
                str(state_path),
                "--issue-number",
                str(ISSUE_NUMBER),
                "--issue-body-file",
                str(issue_path),
                "--head",
                head,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert validated.returncode == 0, validated.stderr
        tampered_binding = deepcopy(state)
        tampered_binding["final_local_review"]["receipt"]["diff_sha256"] = "f" * 64
        state_path.write_text(json.dumps(tampered_binding), encoding="utf-8")
        rejected_binding = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIRECTORY / "review_receipt.py"),
                "validate-full",
                "--repo-root",
                str(repo_root),
                "--process-state",
                str(state_path),
                "--issue-number",
                str(ISSUE_NUMBER),
                "--issue-body-file",
                str(issue_path),
                "--head",
                head,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected_binding.returncode == 2
        assert "diff digest differs from exact Git diff" in rejected_binding.stderr
        state_path.write_text(json.dumps(state), encoding="utf-8")

        remote_root = fixture_root / "remote.git"
        initialized_remote = subprocess.run(
            ["git", "init", "--bare", str(remote_root)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert initialized_remote.returncode == 0, initialized_remote.stderr
        for arguments in (
            ("remote", "add", "origin", str(remote_root)),
            ("push", "origin", "HEAD:refs/heads/reviewed"),
            ("update-ref", "-d", "refs/remotes/origin/reviewed"),
        ):
            completed = subprocess.run(
                ["git", "-C", str(repo_root), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
        local_remote_refs = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "for-each-ref",
                "--format=%(refname)",
                f"--points-at={head}",
                "refs/remotes",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert local_remote_refs.returncode == 0, local_remote_refs.stderr
        assert not local_remote_refs.stdout.strip()

        fetch_only_root = fixture_root / "origin-fetch.git"
        initialized_fetch_only = subprocess.run(
            ["git", "init", "--bare", str(fetch_only_root)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert initialized_fetch_only.returncode == 0, initialized_fetch_only.stderr
        for arguments in (
            ("remote", "set-url", "origin", str(fetch_only_root)),
            ("remote", "set-url", "--push", "origin", str(remote_root)),
        ):
            completed = subprocess.run(
                ["git", "-C", str(repo_root), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
        origin_fetch_heads = subprocess.run(
            ["git", "-C", str(repo_root), "ls-remote", "--heads", "origin"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        assert not origin_fetch_heads

        upstream_root = fixture_root / "upstream.git"
        initialized_upstream = subprocess.run(
            ["git", "init", "--bare", str(upstream_root)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert initialized_upstream.returncode == 0, initialized_upstream.stderr
        branch = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "--show-current"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD^{tree}"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        other_head = subprocess.run(
            ["git", "-C", str(repo_root), "commit-tree", tree, "-m", "other"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        for arguments in (
            ("remote", "add", "upstream", str(upstream_root)),
            ("push", "upstream", f"{other_head}:refs/heads/reviewed"),
            ("fetch", "upstream", "reviewed"),
            ("config", f"branch.{branch}.remote", "upstream"),
            ("config", f"branch.{branch}.merge", "refs/heads/reviewed"),
        ):
            completed = subprocess.run(
                ["git", "-C", str(repo_root), *arguments],
                text=True,
                capture_output=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
        configured_upstream = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "@{upstream}"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        assert configured_upstream == other_head
        assert configured_upstream != head
        pushed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        assert pushed.returncode == 2
        assert "must run before push of the exact HEAD" in pushed.stderr


def main() -> int:
    """Run every function contract without pytest discovery state."""
    _isolate_fixture_git_environment()

    tests = (
        test_issue_normalization_preserves_semantics_expect_canonical_text,
        test_full_receipt_valid_expect_publishable,
        test_full_receipt_stale_and_incomplete_expect_rejected,
        test_identity_and_live_issue_drift_expect_rejected,
        test_blocker_evidence_and_key_uniqueness_expect_enforced,
        test_delta_partition_expect_validator_only,
        test_policy_path_safety_expect_rejected,
        test_push_endpoint_error_expect_credentials_redacted,
        test_build_full_cli_clean_commit_expect_state_receipt,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"review-receipt contract checks passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
