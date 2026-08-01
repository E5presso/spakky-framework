#!/usr/bin/env python3
"""Build and validate exact-head independent review receipts."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import unicodedata


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type AncestryCheck = Callable[[str, str], bool]

CATEGORY_IDS = tuple(f"C{number:02d}" for number in range(1, 15))
DEFAULT_POLICY = Path(".agents/review-criteria-policy.json")
HEX_DIGITS = frozenset("0123456789abcdef")
GIT_TIMEOUT_SECONDS = 30


class ReviewReceiptError(RuntimeError):
    """A review receipt violates the frozen review contract."""


def canonical_json(value: JsonValue) -> str:
    """Serialize a JSON value with the receipt canonicalization contract."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_json(value: JsonValue) -> str:
    """Hash canonical UTF-8 JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_issue_body(issue_body: str) -> str:
    """Normalize live issue text without changing semantic line ordering."""

    normalized = unicodedata.normalize(
        "NFC",
        issue_body.replace("\r\n", "\n").replace("\r", "\n"),
    )
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _json_object(value: JsonValue, name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ReviewReceiptError(f"{name} must be a JSON object")
    if not all(isinstance(key, str) for key in value):
        raise ReviewReceiptError(f"{name} must use string keys")
    return value


def _json_list(value: JsonValue, name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ReviewReceiptError(f"{name} must be a JSON array")
    return value


def _required_string(source: Mapping[str, JsonValue], key: str, owner: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReviewReceiptError(f"{owner}.{key} must be a nonblank string")
    return value


def _required_integer(source: Mapping[str, JsonValue], key: str, owner: str) -> int:
    value = source.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReviewReceiptError(f"{owner}.{key} must be a nonnegative integer")
    return value


def _canonical_identity(
    source: Mapping[str, JsonValue],
    key: str,
    owner: str,
) -> str:
    value = _required_string(source, key, owner)
    normalized = unicodedata.normalize("NFC", value.strip())
    if (
        value != normalized
        or not normalized.isascii()
        or any(
            not (character.isalnum() or character in "._:/@-")
            for character in normalized
        )
    ):
        raise ReviewReceiptError(
            f"{owner}.{key} must be a trimmed NFC identity token using ASCII"
        )
    return normalized


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and set(value) <= HEX_DIGITS


def _is_git_sha(value: str) -> bool:
    return len(value) in {40, 64} and set(value) <= HEX_DIGITS


def _validate_repo_relative_path(value: str, owner: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ReviewReceiptError(f"{owner} must be a canonical repo-relative path")
    return path


def _strict_source(repo_root: Path, value: str) -> Path:
    relative = _validate_repo_relative_path(value, f"criteria source {value!r}")
    root = repo_root.resolve(strict=True)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ReviewReceiptError(f"criteria source traverses symlink: {value}")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
        mode = os.lstat(resolved).st_mode
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ReviewReceiptError(f"criteria source is unavailable: {value}") from error
    if not stat.S_ISREG(mode):
        raise ReviewReceiptError(f"criteria source is not a regular file: {value}")
    if not os.access(resolved, os.R_OK):
        raise ReviewReceiptError(f"criteria source is unreadable: {value}")
    return resolved


def _read_json(path: Path, name: str) -> JsonObject:
    if not path.is_file() or path.is_symlink():
        raise ReviewReceiptError(f"{name} must be a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewReceiptError(f"cannot read {name}: {path}") from error
    return _json_object(value, name)


def _policy_file(repo_root: Path, policy_path: Path | None) -> Path:
    if policy_path is None:
        return repo_root / DEFAULT_POLICY
    return policy_path if policy_path.is_absolute() else repo_root / policy_path


def _required_policy_sources(repo_root: Path, policy_file: Path) -> set[str]:
    root = repo_root.resolve(strict=True)
    try:
        policy_relative = policy_file.resolve(strict=True).relative_to(root).as_posix()
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ReviewReceiptError(
            "criteria policy must be inside the repository"
        ) from error
    required = {policy_relative}
    required.update(
        path.relative_to(root).as_posix()
        for path in (
            root / "AGENTS.md",
            root / ".agents/skills/review-code/SKILL.md",
        )
        if path.is_file()
    )
    for directory in (
        root / ".agents/rules",
        root / ".agents/skills/review-code/personas",
    ):
        if directory.is_dir():
            required.update(
                path.relative_to(root).as_posix()
                for path in directory.glob("*.md")
                if path.is_file()
            )
    return required


def build_criteria_manifest(
    repo_root: Path,
    issue_number: int,
    issue_body: str,
    policy_path: Path | None = None,
) -> JsonObject:
    """Freeze policy sources and the normalized live issue body."""

    if issue_number < 1:
        raise ReviewReceiptError("issue number must be positive")
    policy_file = _policy_file(repo_root, policy_path)
    policy = _read_json(policy_file, "criteria policy")
    if policy.get("schema_version") != 1:
        raise ReviewReceiptError("criteria policy schema_version must be 1")
    categories = _json_list(policy.get("categories"), "criteria policy.categories")
    if categories != list(CATEGORY_IDS):
        raise ReviewReceiptError("criteria policy must declare C01-C14 in order")
    raw_sources = _json_list(policy.get("sources"), "criteria policy.sources")
    sources: list[str] = []
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, str):
            raise ReviewReceiptError(
                f"criteria policy.sources[{index}] must be a string"
            )
        sources.append(raw_source)
    if not sources or len(sources) != len(set(sources)):
        raise ReviewReceiptError("criteria policy sources must be nonempty and unique")
    frozen_sources: list[JsonValue] = []
    for source in sorted(sources):
        path = _strict_source(repo_root, source)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise ReviewReceiptError(
                f"criteria source is unreadable: {source}"
            ) from error
        frozen_sources.append({"path": source, "sha256": digest})
    missing_sources = _required_policy_sources(repo_root, policy_file) - set(sources)
    if missing_sources:
        raise ReviewReceiptError(
            "criteria policy omits required review sources: "
            + ", ".join(sorted(missing_sources))
        )
    body_digest = hashlib.sha256(
        normalize_issue_body(issue_body).encode("utf-8")
    ).hexdigest()
    payload: JsonObject = {
        "schema_version": 1,
        "issue": {"number": issue_number, "body_sha256": body_digest},
        "sources": frozen_sources,
    }
    return {**payload, "criteria_digest": sha256_json(payload)}


def validate_criteria_manifest(
    manifest: JsonObject,
    expected_issue_number: int,
) -> None:
    """Validate the canonical structure and digest of a frozen manifest."""

    if manifest.get("schema_version") != 1:
        raise ReviewReceiptError("manifest schema_version must be 1")
    issue = _json_object(manifest.get("issue"), "manifest.issue")
    if _required_integer(issue, "number", "manifest.issue") != expected_issue_number:
        raise ReviewReceiptError("manifest issue number mismatch")
    body_digest = _required_string(issue, "body_sha256", "manifest.issue")
    if not _is_sha256(body_digest):
        raise ReviewReceiptError("manifest issue digest is not SHA-256")
    sources = _json_list(manifest.get("sources"), "manifest.sources")
    paths: list[str] = []
    for index, raw_source in enumerate(sources):
        source = _json_object(raw_source, f"manifest.sources[{index}]")
        path = _required_string(source, "path", f"manifest.sources[{index}]")
        _validate_repo_relative_path(path, f"manifest.sources[{index}].path")
        digest = _required_string(
            source,
            "sha256",
            f"manifest.sources[{index}]",
        )
        if not _is_sha256(digest):
            raise ReviewReceiptError("manifest source digest is not SHA-256")
        paths.append(path)
    if not paths or paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ReviewReceiptError("manifest sources must be unique and path-sorted")
    expected_digest = sha256_json(
        {
            "schema_version": 1,
            "issue": issue,
            "sources": sources,
        }
    )
    digest = _required_string(manifest, "criteria_digest", "manifest")
    if not _is_sha256(digest) or digest != expected_digest:
        raise ReviewReceiptError("manifest criteria_digest mismatch")


def compute_matrix_digest(rows: list[JsonValue]) -> str:
    """Hash the ordered review matrix."""

    return sha256_json(rows)


def compute_result_digest(
    verdict: str,
    findings: list[JsonValue],
    notes: list[JsonValue],
    *,
    head_sha: str,
    criteria_digest: str,
    reviewer: str,
) -> str:
    """Hash the reviewer result and the exact context it attests."""

    return sha256_json(
        {
            "head_sha": head_sha,
            "criteria_digest": criteria_digest,
            "reviewer": reviewer,
            "verdict": verdict,
            "findings": findings,
            "notes": notes,
        }
    )


def _validate_evidence_paths(raw_paths: JsonValue, owner: str) -> list[str]:
    paths = _json_list(raw_paths, f"{owner}.evidence_paths")
    result: list[str] = []
    for index, raw_path in enumerate(paths):
        if not isinstance(raw_path, str):
            raise ReviewReceiptError(
                f"{owner}.evidence_paths[{index}] must be a string"
            )
        _validate_repo_relative_path(raw_path, f"{owner}.evidence_paths[{index}]")
        result.append(raw_path)
    if not result or len(result) != len(set(result)):
        raise ReviewReceiptError(f"{owner}.evidence_paths must be nonempty and unique")
    return result


def _validate_rows(
    rows: list[JsonValue],
    *,
    allow_inherited: bool,
    manifest_sources: set[str],
) -> tuple[int, int]:
    if len(rows) != len(CATEGORY_IDS):
        raise ReviewReceiptError("receipt must contain exactly 14 matrix rows")
    categories: list[str] = []
    reverified = 0
    inherited = 0
    for index, raw_row in enumerate(rows):
        row = _json_object(raw_row, f"receipt.rows[{index}]")
        category = _required_string(row, "category", f"receipt.rows[{index}]")
        categories.append(category)
        disposition = _required_string(
            row,
            "disposition",
            f"receipt.rows[{index}]",
        )
        evidence_paths = _validate_evidence_paths(
            row.get("evidence_paths"), f"receipt.rows[{index}]"
        )
        ambiguous = row.get("ambiguous")
        if not isinstance(ambiguous, bool):
            raise ReviewReceiptError(f"receipt.rows[{index}].ambiguous must be boolean")
        if disposition == "reverified":
            _required_string(row, "impact_reason", f"receipt.rows[{index}]")
            reverified += 1
            continue
        if disposition != "inherited" or not allow_inherited:
            raise ReviewReceiptError("full receipt rows must all be reverified")
        _required_string(row, "unaffected_reason", f"receipt.rows[{index}]")
        if ambiguous:
            raise ReviewReceiptError("ambiguous rows cannot be inherited")
        if any(path not in manifest_sources for path in evidence_paths):
            raise ReviewReceiptError(
                "inherited evidence must belong to the frozen criteria source set"
            )
        inherited += 1
    if categories != list(CATEGORY_IDS):
        raise ReviewReceiptError(
            "receipt rows must cover C01-C14 exactly once in canonical order"
        )
    return reverified, inherited


def _validate_findings_and_notes(
    findings: list[JsonValue],
    notes: list[JsonValue],
    expected_head: str,
) -> int:
    stable_keys: list[str] = []
    root_cause_keys: list[str] = []
    blocker_count = 0
    for index, raw_finding in enumerate(findings):
        finding = _json_object(raw_finding, f"receipt.findings[{index}]")
        stable_keys.append(
            _required_string(finding, "stable_key", f"receipt.findings[{index}]")
        )
        root_cause_keys.append(
            _required_string(
                finding,
                "root_cause_key",
                f"receipt.findings[{index}]",
            )
        )
        severity = _required_string(
            finding,
            "severity",
            f"receipt.findings[{index}]",
        )
        _required_string(finding, "summary", f"receipt.findings[{index}]")
        if severity == "warning":
            continue
        if severity != "blocker":
            raise ReviewReceiptError("finding severity must be warning or blocker")
        blocker_count += 1
        for key in (
            "observation",
            "expected",
            "actual",
            "acceptance_or_merge_impact",
            "impact",
        ):
            _required_string(finding, key, f"receipt.findings[{index}]")
        reproduction = _json_object(
            finding.get("reproduction"),
            f"receipt.findings[{index}].reproduction",
        )
        _required_string(
            reproduction,
            "command",
            f"receipt.findings[{index}].reproduction",
        )
        if (
            _required_string(
                reproduction,
                "head_sha",
                f"receipt.findings[{index}].reproduction",
            )
            != expected_head
        ):
            raise ReviewReceiptError("blocker reproduction head SHA mismatch")
        _required_integer(
            reproduction,
            "exit_code",
            f"receipt.findings[{index}].reproduction",
        )
        output_digest = _required_string(
            reproduction,
            "output_digest",
            f"receipt.findings[{index}].reproduction",
        )
        if not _is_sha256(output_digest):
            raise ReviewReceiptError(
                "blocker reproduction output_digest must be SHA-256"
            )
    for index, raw_note in enumerate(notes):
        note = _json_object(raw_note, f"receipt.notes[{index}]")
        stable_keys.append(
            _required_string(note, "stable_key", f"receipt.notes[{index}]")
        )
        root_cause_keys.append(
            _required_string(note, "root_cause_key", f"receipt.notes[{index}]")
        )
        _required_string(note, "text", f"receipt.notes[{index}]")
    if len(stable_keys) != len(set(stable_keys)):
        raise ReviewReceiptError("stable keys must be unique across findings and notes")
    if len(root_cause_keys) != len(set(root_cause_keys)):
        raise ReviewReceiptError(
            "root-cause keys must be unique across findings and notes"
        )
    return blocker_count


def _manifest_source_set(manifest: JsonObject) -> set[str]:
    sources = _json_list(manifest.get("sources"), "manifest.sources")
    return {
        _required_string(
            _json_object(item, "manifest source"),
            "path",
            "manifest source",
        )
        for item in sources
    }


def _validate_receipt_common(
    receipt: JsonObject,
    manifest: JsonObject,
    expected_head: str,
    expected_issue_number: int,
    *,
    allow_inherited: bool,
) -> tuple[int, int, int]:
    validate_criteria_manifest(manifest, expected_issue_number)
    if receipt.get("schema_version") != 1:
        raise ReviewReceiptError("receipt schema_version must be 1")
    head = _required_string(receipt, "head_sha", "receipt")
    if not _is_git_sha(head) or head != expected_head:
        raise ReviewReceiptError("receipt head SHA mismatch")
    base_sha = _required_string(receipt, "base_sha", "receipt")
    if not _is_git_sha(base_sha):
        raise ReviewReceiptError("receipt base SHA is invalid")
    diff_sha256 = _required_string(receipt, "diff_sha256", "receipt")
    if not _is_sha256(diff_sha256):
        raise ReviewReceiptError("receipt diff digest is invalid")
    if _required_integer(receipt, "issue_number", "receipt") != expected_issue_number:
        raise ReviewReceiptError("receipt issue number mismatch")
    if _required_string(receipt, "criteria_digest", "receipt") != manifest.get(
        "criteria_digest"
    ):
        raise ReviewReceiptError("receipt criteria digest mismatch")
    owner = _canonical_identity(receipt, "owner", "receipt")
    implementer = _canonical_identity(receipt, "implementer", "receipt")
    reviewer = _canonical_identity(receipt, "reviewer", "receipt")
    if reviewer.casefold() in {owner.casefold(), implementer.casefold()}:
        raise ReviewReceiptError("reviewer must differ from owner and implementer")
    rows = _json_list(receipt.get("rows"), "receipt.rows")
    reverified, inherited = _validate_rows(
        rows,
        allow_inherited=allow_inherited,
        manifest_sources=_manifest_source_set(manifest),
    )
    if _required_string(receipt, "matrix_digest", "receipt") != compute_matrix_digest(
        rows
    ):
        raise ReviewReceiptError("receipt matrix digest mismatch")
    findings = _json_list(receipt.get("findings"), "receipt.findings")
    notes = _json_list(receipt.get("notes"), "receipt.notes")
    verdict = _required_string(receipt, "verdict", "receipt")
    if verdict not in {"PASS", "BLOCK"}:
        raise ReviewReceiptError("receipt verdict must be PASS or BLOCK")
    blockers = _validate_findings_and_notes(findings, notes, expected_head)
    if _required_integer(receipt, "blocker_count", "receipt") != blockers:
        raise ReviewReceiptError("receipt blocker_count mismatch")
    if verdict == "PASS" and blockers != 0:
        raise ReviewReceiptError("PASS receipt cannot contain blockers")
    if verdict == "BLOCK" and blockers == 0:
        raise ReviewReceiptError("BLOCK receipt must contain a blocker")
    expected_result = compute_result_digest(
        verdict,
        findings,
        notes,
        head_sha=head,
        criteria_digest=_required_string(receipt, "criteria_digest", "receipt"),
        reviewer=reviewer,
    )
    if _required_string(receipt, "result_digest", "receipt") != expected_result:
        raise ReviewReceiptError("receipt result digest mismatch")
    return reverified, inherited, blockers


def validate_full_receipt(
    receipt: JsonObject,
    manifest: JsonObject,
    expected_head: str,
    expected_issue_number: int,
) -> None:
    """Validate a structurally complete full PASS or BLOCK receipt."""

    if receipt.get("mode") != "full":
        raise ReviewReceiptError("full receipt mode must be 'full'")
    reverified, inherited, _ = _validate_receipt_common(
        receipt,
        manifest,
        expected_head,
        expected_issue_number,
        allow_inherited=False,
    )
    if reverified != len(CATEGORY_IDS) or inherited != 0:
        raise ReviewReceiptError("full receipt must be 14/14 reverified")


def validate_publishable_full_receipt(
    receipt: JsonObject,
    manifest: JsonObject,
    expected_head: str,
    expected_issue_number: int,
) -> None:
    """Validate the stricter first-rollout publication contract."""

    validate_full_receipt(receipt, manifest, expected_head, expected_issue_number)
    if receipt.get("verdict") != "PASS" or receipt.get("blocker_count") != 0:
        raise ReviewReceiptError("only blocker-free PASS receipt is publishable")


def validate_delta_receipt(
    receipt: JsonObject,
    prior_receipt: JsonObject,
    manifest: JsonObject,
    is_ancestor: AncestryCheck,
) -> None:
    """Validate proven-delta inheritance without making it publishable."""

    issue_number = _required_integer(receipt, "issue_number", "receipt")
    prior_head = _required_string(receipt, "prior_head_sha", "receipt")
    current_head = _required_string(receipt, "head_sha", "receipt")
    validate_publishable_full_receipt(
        prior_receipt,
        manifest,
        prior_head,
        issue_number,
    )
    if receipt.get("mode") != "delta":
        raise ReviewReceiptError("delta receipt mode must be 'delta'")
    if prior_receipt.get("head_sha") != prior_head or prior_head == current_head:
        raise ReviewReceiptError("delta prior/current head relationship is invalid")
    if prior_receipt.get("criteria_digest") != receipt.get("criteria_digest"):
        raise ReviewReceiptError("delta criteria digest differs from prior PASS")
    if not is_ancestor(prior_head, current_head):
        raise ReviewReceiptError("prior full PASS is not an ancestor")
    reverified, _, blockers = _validate_receipt_common(
        receipt,
        manifest,
        current_head,
        issue_number,
        allow_inherited=True,
    )
    if reverified < 1:
        raise ReviewReceiptError("delta receipt must reverify at least one row")
    if receipt.get("verdict") != "PASS" or blockers != 0:
        raise ReviewReceiptError("delta inheritance requires blocker-free PASS")


def _validate_final_review_delegate(
    state: Mapping[str, JsonValue],
    expected_head: str,
    expected_criteria_digest: str,
) -> str:
    delegate = _json_object(
        state.get("final_review_delegate"),
        "process state.final_review_delegate",
    )
    if (
        _required_string(
            delegate,
            "head_sha",
            "process state.final_review_delegate",
        )
        != expected_head
    ):
        raise ReviewReceiptError("final review delegate head SHA mismatch")
    if (
        _required_string(
            delegate,
            "criteria_digest",
            "process state.final_review_delegate",
        )
        != expected_criteria_digest
    ):
        raise ReviewReceiptError("final review delegate criteria digest mismatch")
    return _canonical_identity(
        delegate,
        "reviewer",
        "process state.final_review_delegate",
    )


def validate_process_state_full_receipt(
    process_state: Mapping[str, JsonValue],
    repo_root: Path,
    live_issue_body: str,
    expected_head: str,
    expected_issue_number: int,
    policy_path: Path | None = None,
) -> JsonObject:
    """Rebuild live criteria and validate a publishable process-state receipt."""

    state = dict(process_state)
    final_review = _json_object(
        state.get("final_local_review"),
        "process state.final_local_review",
    )
    stored_manifest = _json_object(
        final_review.get("manifest"),
        "process state.final_local_review.manifest",
    )
    receipt = _json_object(
        final_review.get("receipt"),
        "process state.final_local_review.receipt",
    )
    live_manifest = build_criteria_manifest(
        repo_root,
        expected_issue_number,
        live_issue_body,
        policy_path,
    )
    if canonical_json(stored_manifest) != canonical_json(live_manifest):
        raise ReviewReceiptError("stored criteria manifest differs from live criteria")
    if state.get("commit_done") != expected_head:
        raise ReviewReceiptError("process state commit_done differs from expected head")
    owner = _canonical_identity(state, "owner", "process state")
    implementer = _canonical_identity(state, "implementer", "process state")
    delegate_reviewer = _validate_final_review_delegate(
        state,
        expected_head,
        _required_string(live_manifest, "criteria_digest", "manifest"),
    )
    if receipt.get("owner") != owner:
        raise ReviewReceiptError("process state owner differs from receipt")
    if receipt.get("implementer") != implementer:
        raise ReviewReceiptError("process state implementer differs from receipt")
    if receipt.get("reviewer") != delegate_reviewer:
        raise ReviewReceiptError("final review delegate reviewer differs from receipt")
    expected_base_sha = _git(repo_root, "merge-base", "origin/develop", expected_head)
    if receipt.get("base_sha") != expected_base_sha:
        raise ReviewReceiptError("receipt base differs from origin/develop merge-base")
    expected_diff = _git_bytes(
        repo_root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--no-textconv",
        f"{expected_base_sha}...{expected_head}",
    )
    if receipt.get("diff_sha256") != hashlib.sha256(expected_diff).hexdigest():
        raise ReviewReceiptError("receipt diff digest differs from exact Git diff")
    validate_publishable_full_receipt(
        receipt,
        live_manifest,
        expected_head,
        expected_issue_number,
    )
    return receipt


def _build_receipt(
    result: JsonObject,
    manifest: JsonObject,
    *,
    head: str,
    issue_number: int,
    owner: str,
    implementer: str,
    expected_reviewer: str,
    expected_base_sha: str,
    expected_diff_sha256: str,
) -> JsonObject:
    result_head = _required_string(result, "head_sha", "review result")
    if result_head != head:
        raise ReviewReceiptError("review result head SHA mismatch")
    criteria_digest = _required_string(
        result,
        "criteria_digest",
        "review result",
    )
    if criteria_digest != manifest.get("criteria_digest"):
        raise ReviewReceiptError("review result criteria digest mismatch")
    reviewer = _canonical_identity(result, "reviewer", "review result")
    if reviewer != expected_reviewer:
        raise ReviewReceiptError("review result reviewer differs from delegate")
    if _required_string(result, "base_sha", "review result") != expected_base_sha:
        raise ReviewReceiptError("review result base SHA mismatch")
    if _required_string(result, "diff_sha256", "review result") != expected_diff_sha256:
        raise ReviewReceiptError("review result diff digest mismatch")
    canonical_owner = _canonical_identity({"owner": owner}, "owner", "build")
    canonical_implementer = _canonical_identity(
        {"implementer": implementer},
        "implementer",
        "build",
    )
    rows = _json_list(result.get("rows"), "review result.rows")
    findings = _json_list(result.get("findings"), "review result.findings")
    notes = _json_list(result.get("notes"), "review result.notes")
    verdict = _required_string(result, "verdict", "review result")
    blockers = sum(
        1
        for raw_finding in findings
        if _json_object(raw_finding, "review result finding").get("severity")
        == "blocker"
    )
    receipt: JsonObject = {
        "schema_version": 1,
        "mode": "full",
        "head_sha": head,
        "base_sha": expected_base_sha,
        "diff_sha256": expected_diff_sha256,
        "issue_number": issue_number,
        "criteria_digest": criteria_digest,
        "matrix_digest": compute_matrix_digest(rows),
        "result_digest": compute_result_digest(
            verdict,
            findings,
            notes,
            head_sha=result_head,
            criteria_digest=criteria_digest,
            reviewer=reviewer,
        ),
        "owner": canonical_owner,
        "implementer": canonical_implementer,
        "reviewer": reviewer,
        "verdict": verdict,
        "rows": rows,
        "findings": findings,
        "notes": notes,
        "blocker_count": blockers,
    }
    validate_full_receipt(receipt, manifest, head, issue_number)
    return receipt


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
        raise ReviewReceiptError(
            f"git {' '.join(arguments)} timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReviewReceiptError(
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
        raise ReviewReceiptError(
            f"git {' '.join(arguments)} timed out after {GIT_TIMEOUT_SECONDS}s"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        if not detail:
            detail = completed.stdout.decode("utf-8", errors="replace").strip()
        raise ReviewReceiptError(
            f"git {' '.join(arguments)} failed ({completed.returncode}): {detail}"
        )
    return completed.stdout


def _optional_git_config(repo_root: Path, key: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "config", "--get", key],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 1 and not completed.stdout.strip():
        return None
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReviewReceiptError(
            f"git config --get {key} failed ({completed.returncode}): {detail}"
        )
    value = completed.stdout.strip()
    if not value:
        raise ReviewReceiptError(f"git config --get {key} returned an empty value")
    return value


def _remote_heads_for_endpoint(repo_root: Path, endpoint: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-remote", "--heads", endpoint],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as error:
        raise ReviewReceiptError(
            "git ls-remote timed out for a configured push endpoint"
        ) from error
    if completed.returncode != 0:
        raise ReviewReceiptError(
            "git ls-remote failed for a configured push endpoint "
            f"({completed.returncode})"
        )
    return completed.stdout.strip()


def _reject_already_pushed_head(repo_root: Path, head: str) -> None:
    exact_remote_refs = _git(
        repo_root,
        "for-each-ref",
        "--format=%(refname)",
        f"--points-at={head}",
        "refs/remotes",
    )
    if exact_remote_refs:
        raise ReviewReceiptError("build-full must run before push of the exact HEAD")
    branch = _git(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD")
    remote = _optional_git_config(repo_root, f"branch.{branch}.remote")
    merge = _optional_git_config(repo_root, f"branch.{branch}.merge")
    remotes = set(_git(repo_root, "remote").splitlines())
    remotes_to_check = set()
    if "origin" in remotes:
        remotes_to_check.add("origin")
    if remote is not None and (remote in remotes or remote == "."):
        remotes_to_check.add(remote)
    endpoints: set[str] = set()
    for remote_to_check in sorted(remotes_to_check):
        if remote_to_check == ".":
            endpoints.add(remote_to_check)
            continue
        push_urls = _git(
            repo_root,
            "remote",
            "get-url",
            "--all",
            "--push",
            remote_to_check,
        ).splitlines()
        if not push_urls:
            raise ReviewReceiptError(
                f"configured remote has no push endpoint: {remote_to_check}"
            )
        endpoints.update(push_urls)
    for endpoint in sorted(endpoints):
        remote_heads = _remote_heads_for_endpoint(repo_root, endpoint)
        if any(
            line.split(maxsplit=1)[0] == head
            for line in remote_heads.splitlines()
            if line.strip()
        ):
            raise ReviewReceiptError(
                "build-full must run before push of the exact HEAD"
            )
    if remote is None and merge is None:
        return
    if remote is None or merge is None:
        raise ReviewReceiptError(
            "current branch has an incomplete upstream configuration"
        )
    if _git(repo_root, "rev-parse", "--verify", "@{upstream}") == head:
        raise ReviewReceiptError("build-full must run before push of the exact HEAD")


def _require_process_state_path(repo_root: Path, process_state_path: Path) -> None:
    if process_state_path.resolve() != repo_root / ".process-state.json":
        raise ReviewReceiptError(
            "process state must be the worktree .process-state.json"
        )


def validate_final_review_inputs(
    process_state: Mapping[str, JsonValue],
    repo_root: Path,
    policy_path: Path | None = None,
) -> JsonObject:
    """Rehydrate and validate delegated final-review inputs after an idle turn."""

    root = repo_root.resolve(strict=True)
    state = dict(process_state)
    if state.get("worktree") != str(root):
        raise ReviewReceiptError("process state worktree mismatch")
    issue_number = _required_integer(state, "issue_number", "process state")
    if issue_number < 1:
        raise ReviewReceiptError("process state issue number must be positive")
    head = _required_string(state, "commit_done", "process state")
    if not _is_git_sha(head) or _git(root, "rev-parse", "HEAD") != head:
        raise ReviewReceiptError("final review input head differs from committed HEAD")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ReviewReceiptError("final review input worktree is dirty")
    inputs = _json_object(
        state.get("final_review_inputs"),
        "process state.final_review_inputs",
    )
    if _required_string(inputs, "head_sha", "final review inputs") != head:
        raise ReviewReceiptError("final review input head SHA mismatch")

    temp_root_value = os.environ.get("TMPDIR") or "/tmp"
    try:
        temp_root = Path(temp_root_value).resolve(strict=True)
        raw_directory = _required_string(inputs, "temp_dir", "final review inputs")
        directory = Path(raw_directory)
        resolved_directory = directory.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ReviewReceiptError(
            "final review input directory is unavailable"
        ) from error
    expected_prefix = f"spakky-final-review-{issue_number}."
    if (
        not directory.is_absolute()
        or directory.is_symlink()
        or str(resolved_directory) != raw_directory
        or resolved_directory.parent != temp_root
        or not resolved_directory.name.startswith(expected_prefix)
        or not resolved_directory.is_dir()
    ):
        raise ReviewReceiptError("final review input directory is not canonical")

    expected_paths = {
        "manifest_path": resolved_directory / "criteria-manifest.json",
        "issue_body_path": resolved_directory / "issue-body.md",
        "diff_path": resolved_directory / "committed.diff",
    }
    validated_paths: dict[str, str] = {}
    for key, expected_path in expected_paths.items():
        raw_path = _required_string(inputs, key, "final review inputs")
        path = Path(raw_path)
        if raw_path != str(expected_path) or not path.is_file() or path.is_symlink():
            raise ReviewReceiptError(f"final review input {key} is not canonical")
        validated_paths[key] = raw_path

    issue_body = _issue_body(Path(validated_paths["issue_body_path"]))
    live_manifest = build_criteria_manifest(
        root,
        issue_number,
        issue_body,
        policy_path,
    )
    stored_manifest = _read_json(
        Path(validated_paths["manifest_path"]),
        "final review input manifest",
    )
    if canonical_json(stored_manifest) != canonical_json(live_manifest):
        raise ReviewReceiptError(
            "final review input manifest differs from live criteria"
        )
    criteria_digest = _required_string(
        inputs,
        "criteria_digest",
        "final review inputs",
    )
    if criteria_digest != live_manifest.get("criteria_digest"):
        raise ReviewReceiptError("final review input criteria digest mismatch")
    base_sha = _required_string(inputs, "base_sha", "final review inputs")
    if not _is_git_sha(base_sha):
        raise ReviewReceiptError("final review input base SHA is invalid")
    if _git(root, "merge-base", "origin/develop", head) != base_sha:
        raise ReviewReceiptError(
            "final review input base differs from origin/develop merge-base"
        )
    expected_diff = _git_bytes(
        root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--no-textconv",
        f"{base_sha}...{head}",
    )
    diff_path = Path(validated_paths["diff_path"])
    try:
        actual_diff = diff_path.read_bytes()
    except OSError as error:
        raise ReviewReceiptError("cannot read final review committed diff") from error
    if actual_diff != expected_diff:
        raise ReviewReceiptError(
            "final review committed diff differs from the exact Git diff"
        )
    diff_sha256 = _required_string(
        inputs,
        "diff_sha256",
        "final review inputs",
    )
    expected_diff_sha256 = hashlib.sha256(expected_diff).hexdigest()
    if not _is_sha256(diff_sha256) or diff_sha256 != expected_diff_sha256:
        raise ReviewReceiptError("final review input diff digest mismatch")
    return {
        "temp_dir": str(resolved_directory),
        **validated_paths,
        "head_sha": head,
        "criteria_digest": criteria_digest,
        "base_sha": base_sha,
        "diff_sha256": diff_sha256,
    }


def _write_state(path: Path, state: JsonObject) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def cleanup_final_review_inputs(
    process_state_path: Path,
    repo_root: Path,
    policy_path: Path | None = None,
) -> JsonObject:
    """Consume validated handoff inputs after a matching full receipt is durable."""

    root = repo_root.resolve(strict=True)
    _require_process_state_path(root, process_state_path)
    state = _read_json(process_state_path, "process state")
    inputs = validate_final_review_inputs(state, root, policy_path)
    issue_number = _required_integer(state, "issue_number", "process state")
    head = _required_string(state, "commit_done", "process state")
    final_review = _json_object(
        state.get("final_local_review"),
        "process state.final_local_review",
    )
    stored_manifest = _json_object(
        final_review.get("manifest"),
        "process state.final_local_review.manifest",
    )
    input_manifest = _read_json(
        Path(str(inputs["manifest_path"])),
        "final review input manifest",
    )
    if canonical_json(stored_manifest) != canonical_json(input_manifest):
        raise ReviewReceiptError(
            "stored receipt manifest differs from final review inputs"
        )
    receipt = _json_object(
        final_review.get("receipt"),
        "process state.final_local_review.receipt",
    )
    owner = _canonical_identity(state, "owner", "process state")
    implementer = _canonical_identity(state, "implementer", "process state")
    reviewer = _validate_final_review_delegate(
        state,
        head,
        _required_string(stored_manifest, "criteria_digest", "manifest"),
    )
    result_path = Path(str(inputs["temp_dir"])) / "review-result.json"
    if not result_path.is_file() or result_path.is_symlink():
        raise ReviewReceiptError("final review result is not a canonical regular file")
    result = _read_json(result_path, "review result")
    rebuilt_receipt = _build_receipt(
        result,
        stored_manifest,
        head=head,
        issue_number=issue_number,
        owner=owner,
        implementer=implementer,
        expected_reviewer=reviewer,
        expected_base_sha=str(inputs["base_sha"]),
        expected_diff_sha256=str(inputs["diff_sha256"]),
    )
    if canonical_json(receipt) != canonical_json(rebuilt_receipt):
        raise ReviewReceiptError("durable receipt differs from the final review result")
    validate_full_receipt(receipt, stored_manifest, head, issue_number)
    verdict = _required_string(receipt, "verdict", "receipt")
    publication = _json_object(state.get("publication"), "process state.publication")
    if publication.get("head_sha") != head:
        raise ReviewReceiptError("publication head differs from final review inputs")
    publication_state = _required_string(publication, "state", "publication")
    if verdict == "BLOCK":
        if publication_state != "incomplete" or publication.get("error") != (
            "final review BLOCK"
        ):
            raise ReviewReceiptError(
                "BLOCK receipt requires the canonical incomplete publication state"
            )
    elif publication_state not in {"pending", "incomplete", "published"}:
        raise ReviewReceiptError("PASS receipt has an unsupported publication state")

    cleanup_paths = [
        result_path,
        Path(str(inputs["diff_path"])),
        Path(str(inputs["issue_body_path"])),
        Path(str(inputs["manifest_path"])),
    ]
    directory = Path(str(inputs["temp_dir"]))
    state.pop("final_review_inputs")
    state["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _write_state(process_state_path, state)
    try:
        for path in cleanup_paths:
            path.unlink()
        directory.rmdir()
    except OSError as error:
        raise ReviewReceiptError(
            "final review input state was consumed but temporary cleanup failed"
        ) from error
    return {"head_sha": head, "verdict": verdict, "state": "consumed"}


def _issue_body(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ReviewReceiptError(f"issue body must be a regular file: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReviewReceiptError(f"cannot read issue body: {path}") from error


def _command_manifest(arguments: argparse.Namespace) -> None:
    manifest = build_criteria_manifest(
        arguments.repo_root,
        arguments.issue_number,
        _issue_body(arguments.issue_body_file),
        arguments.policy,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


def _command_resume_inputs(arguments: argparse.Namespace) -> None:
    repo_root = arguments.repo_root.resolve(strict=True)
    _require_process_state_path(repo_root, arguments.process_state)
    state = _read_json(arguments.process_state, "process state")
    inputs = validate_final_review_inputs(state, repo_root, arguments.policy)
    print(json.dumps(inputs, ensure_ascii=False, indent=2, sort_keys=True))


def _command_cleanup_inputs(arguments: argparse.Namespace) -> None:
    result = cleanup_final_review_inputs(
        arguments.process_state,
        arguments.repo_root,
        arguments.policy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _command_build_full(arguments: argparse.Namespace) -> None:
    repo_root = arguments.repo_root.resolve(strict=True)
    _require_process_state_path(repo_root, arguments.process_state)
    if _git(repo_root, "rev-parse", "HEAD") != arguments.head:
        raise ReviewReceiptError("build-full head differs from local HEAD")
    if _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ReviewReceiptError("build-full requires a clean committed worktree")
    _reject_already_pushed_head(repo_root, arguments.head)
    state = _read_json(arguments.process_state, "process state")
    if state.get("worktree") != str(repo_root):
        raise ReviewReceiptError("process state worktree mismatch")
    if (
        _required_integer(state, "issue_number", "process state")
        != arguments.issue_number
    ):
        raise ReviewReceiptError("process state issue number mismatch")
    if state.get("commit_done") != arguments.head:
        raise ReviewReceiptError("process state commit_done differs from build head")
    review_inputs = validate_final_review_inputs(state, repo_root, arguments.policy)
    if str(arguments.issue_body_file.resolve()) != review_inputs.get("issue_body_path"):
        raise ReviewReceiptError("build-full issue body differs from review inputs")
    expected_result_path = Path(str(review_inputs["temp_dir"])) / "review-result.json"
    if arguments.review_result.resolve() != expected_result_path:
        raise ReviewReceiptError("build-full review result path is not canonical")
    owner = _canonical_identity(state, "owner", "process state")
    implementer = _canonical_identity(state, "implementer", "process state")
    manifest = build_criteria_manifest(
        repo_root,
        arguments.issue_number,
        _issue_body(arguments.issue_body_file),
        arguments.policy,
    )
    expected_reviewer = _validate_final_review_delegate(
        state,
        arguments.head,
        _required_string(manifest, "criteria_digest", "manifest"),
    )
    result = _read_json(arguments.review_result, "review result")
    receipt = _build_receipt(
        result,
        manifest,
        head=arguments.head,
        issue_number=arguments.issue_number,
        owner=owner,
        implementer=implementer,
        expected_reviewer=expected_reviewer,
        expected_base_sha=str(review_inputs["base_sha"]),
        expected_diff_sha256=str(review_inputs["diff_sha256"]),
    )
    state["final_local_review"] = {"manifest": manifest, "receipt": receipt}
    publication: JsonObject = {
        "state": "pending" if receipt["verdict"] == "PASS" else "incomplete",
        "head_sha": arguments.head,
    }
    if receipt["verdict"] == "BLOCK":
        publication["error"] = "final review BLOCK"
    state["publication"] = publication
    state["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _write_state(arguments.process_state, state)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    if receipt["verdict"] != "PASS":
        raise ReviewReceiptError("final review BLOCK; push is forbidden")


def _command_validate_full(arguments: argparse.Namespace) -> None:
    state = _read_json(arguments.process_state, "process state")
    receipt = validate_process_state_full_receipt(
        state,
        arguments.repo_root,
        _issue_body(arguments.issue_body_file),
        arguments.head,
        arguments.issue_number,
        arguments.policy,
    )
    print(canonical_json(receipt))


def _command_validate_delta(arguments: argparse.Namespace) -> None:
    receipt = _read_json(arguments.receipt, "delta receipt")
    prior = _read_json(arguments.prior_receipt, "prior receipt")
    manifest = build_criteria_manifest(
        arguments.repo_root,
        arguments.issue_number,
        _issue_body(arguments.issue_body_file),
        arguments.policy,
    )

    def is_ancestor(prior_head: str, current_head: str) -> bool:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(arguments.repo_root),
                "merge-base",
                "--is-ancestor",
                prior_head,
                current_head,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            return True
        if completed.returncode == 1:
            return False
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReviewReceiptError(f"git ancestry check failed: {detail}")

    validate_delta_receipt(receipt, prior, manifest, is_ancestor)
    print(canonical_json(receipt))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_manifest_inputs(command: argparse.ArgumentParser) -> None:
        command.add_argument("--repo-root", type=Path, required=True)
        command.add_argument("--issue-number", type=int, required=True)
        command.add_argument("--issue-body-file", type=Path, required=True)
        command.add_argument("--policy", type=Path)

    manifest = subparsers.add_parser("manifest")
    add_manifest_inputs(manifest)
    manifest.set_defaults(handler=_command_manifest)

    resume_inputs = subparsers.add_parser("resume-inputs")
    resume_inputs.add_argument("--repo-root", type=Path, required=True)
    resume_inputs.add_argument("--process-state", type=Path, required=True)
    resume_inputs.add_argument("--policy", type=Path)
    resume_inputs.set_defaults(handler=_command_resume_inputs)

    cleanup_inputs = subparsers.add_parser("cleanup-inputs")
    cleanup_inputs.add_argument("--repo-root", type=Path, required=True)
    cleanup_inputs.add_argument("--process-state", type=Path, required=True)
    cleanup_inputs.add_argument("--policy", type=Path)
    cleanup_inputs.set_defaults(handler=_command_cleanup_inputs)

    build = subparsers.add_parser("build-full")
    add_manifest_inputs(build)
    build.add_argument("--process-state", type=Path, required=True)
    build.add_argument("--review-result", type=Path, required=True)
    build.add_argument("--head", required=True)
    build.set_defaults(handler=_command_build_full)

    validate_full = subparsers.add_parser("validate-full")
    add_manifest_inputs(validate_full)
    validate_full.add_argument("--process-state", type=Path, required=True)
    validate_full.add_argument("--head", required=True)
    validate_full.set_defaults(handler=_command_validate_full)

    validate_delta = subparsers.add_parser("validate-delta")
    add_manifest_inputs(validate_delta)
    validate_delta.add_argument("--receipt", type=Path, required=True)
    validate_delta.add_argument("--prior-receipt", type=Path, required=True)
    validate_delta.set_defaults(handler=_command_validate_delta)
    return parser


def main() -> int:
    """Run the receipt contract CLI."""

    arguments = _parser().parse_args()
    try:
        arguments.handler(arguments)
    except ReviewReceiptError as error:
        print(f"review-receipt-invalid: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
