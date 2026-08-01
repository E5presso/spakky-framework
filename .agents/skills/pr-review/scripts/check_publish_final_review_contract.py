"""Offline contract checks for the deterministic final-review publisher."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import cast, override


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIRECTORY))
from publish_final_review import (  # noqa: E402 - contract imports sibling script
    CommandError,
    ICommandRunner,
    PublicationError,
    publish_final_review,
)
from review_receipt import (  # noqa: E402 - loaded by publisher
    CATEGORY_IDS,
    JsonObject,
    JsonValue,
    ReviewReceiptError,
    build_criteria_manifest,
    compute_matrix_digest,
    compute_result_digest,
)
from resolve_review_mode import (  # noqa: E402 - contract imports sibling script
    MANUAL_VERDICTS,
    ReviewModeError,
    resolve_review_mode,
)


HEAD = "a" * 40
REPOSITORY = "E5presso/spakky-framework"
ISSUE_NUMBER = 527
PR_NUMBER = 99
PR_URL = f"https://github.com/{REPOSITORY}/pull/{PR_NUMBER}"
ISSUE_BODY = "frozen issue body\n"


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


class FakeCommandRunner(ICommandRunner):
    """Stateful git/GitHub boundary with an external-mutation ledger."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.local_head: str = HEAD
        self.upstream_head: str = HEAD
        self.dirty = ""
        self.issue_body = ISSUE_BODY
        self.pr_head: str = HEAD
        self.pr_state = "open"
        self.pr_draft = False
        self.head_repo = REPOSITORY
        self.base_repo = REPOSITORY
        self.actor = "publisher"
        self.roles: dict[str, str] = {
            "publisher": "maintain",
            "trusted": "admin",
            "untrusted": "write",
        }
        self.permission_failures: set[str] = set()
        self.comments: list[dict[str, object]] = []
        self.labels: set[str] = set()
        self.statuses: list[dict[str, object]] = []
        self.mutations: list[str] = []
        self.post_status_race = False
        self.post_status_comment_demote = False

    @override
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> str:
        del cwd
        command = tuple(argv)
        if command == ("git", "rev-parse", "--show-toplevel"):
            return f"{self.repo_root}\n"
        if command[:3] == ("git", "-C", str(self.repo_root)):
            return self._run_git(command[3:])
        if command == ("gh", "repo", "view", "--json", "nameWithOwner"):
            return self._dump({"nameWithOwner": REPOSITORY})
        if command[:2] == ("gh", "api"):
            return self._run_gh_api(command[2:], input_text)
        raise CommandError(f"unhandled fake command: {' '.join(command)}")

    def _run_git(self, arguments: Sequence[str]) -> str:
        if tuple(arguments) == (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            return self.dirty
        if tuple(arguments) == ("rev-parse", "HEAD"):
            return f"{self.local_head}\n"
        if tuple(arguments) == ("rev-parse", "@{upstream}"):
            return f"{self.upstream_head}\n"
        raise CommandError(f"unhandled fake git: {' '.join(arguments)}")

    def _run_gh_api(
        self,
        arguments: Sequence[str],
        input_text: str | None,
    ) -> str:
        if tuple(arguments) == ("user",):
            return self._dump({"login": self.actor})
        if len(arguments) >= 3 and arguments[:2] == ("-X", "POST"):
            return self._mutate(arguments[2], input_text)
        endpoint = arguments[-1]
        if endpoint == f"repos/{REPOSITORY}/issues/{ISSUE_NUMBER}":
            return self._dump({"number": ISSUE_NUMBER, "body": self.issue_body})
        if endpoint == f"repos/{REPOSITORY}/pulls/{PR_NUMBER}":
            return self._dump(self._pr())
        if endpoint == (f"repos/{REPOSITORY}/issues/{PR_NUMBER}/comments?per_page=100"):
            return self._dump([self.comments])
        if endpoint == (
            f"repos/{REPOSITORY}/commits/{self.local_head}/statuses?per_page=100"
        ):
            return self._dump([self.statuses])
        permission_prefix = f"repos/{REPOSITORY}/collaborators/"
        if endpoint.startswith(permission_prefix) and endpoint.endswith("/permission"):
            login = endpoint.removeprefix(permission_prefix).removesuffix("/permission")
            if login in self.permission_failures:
                raise CommandError(f"permission unavailable: {login}")
            return self._dump({"role_name": self.roles.get(login, "none")})
        raise CommandError(f"unhandled fake gh api: {endpoint}")

    def _mutate(self, endpoint: str, input_text: str | None) -> str:
        payload = json.loads(input_text or "{}")
        if endpoint == f"repos/{REPOSITORY}/issues/{PR_NUMBER}/comments":
            self.mutations.append("comment")
            identifier = (
                max(
                    [cast(int, comment["id"]) for comment in self.comments],
                    default=100,
                )
                + 1
            )
            comment = {
                "id": identifier,
                "html_url": f"{PR_URL}#issuecomment-{identifier}",
                "body": payload["body"],
                "user": {"login": self.actor},
            }
            self.comments.append(comment)
            return self._dump(comment)
        if endpoint == f"repos/{REPOSITORY}/issues/{PR_NUMBER}/labels":
            self.mutations.append("label")
            self.labels.update(cast(list[str], payload["labels"]))
            return self._dump([{"name": label} for label in sorted(self.labels)])
        if endpoint == f"repos/{REPOSITORY}/statuses/{self.local_head}":
            self.mutations.append("status")
            identifier = (
                max(
                    [cast(int, status["id"]) for status in self.statuses],
                    default=200,
                )
                + 1
            )
            status = {
                "id": identifier,
                "context": payload["context"],
                "state": payload["state"],
                "creator": {"login": self.actor},
            }
            self.statuses.append(status)
            if self.post_status_comment_demote:
                self.roles[self.actor] = "write"
            if self.post_status_race:
                self.statuses.append(
                    {
                        "id": identifier + 1,
                        "context": "ai-review",
                        "state": "failure",
                        "creator": {"login": "untrusted"},
                    }
                )
            return self._dump(status)
        raise CommandError(f"unhandled fake mutation: {endpoint}")

    def _pr(self) -> dict[str, object]:
        return {
            "number": PR_NUMBER,
            "state": self.pr_state,
            "draft": self.pr_draft,
            "html_url": PR_URL,
            "head": {
                "sha": self.pr_head,
                "repo": {"full_name": self.head_repo},
            },
            "base": {"repo": {"full_name": self.base_repo}},
            "labels": [{"name": label} for label in sorted(self.labels)],
        }

    @staticmethod
    def _dump(value: object) -> str:
        return json.dumps(value, ensure_ascii=False)


def _receipt(
    *,
    mode: str = "full",
    verdict: str = "PASS",
    head_sha: str = HEAD,
) -> JsonObject:
    return {
        "schema_version": 1,
        "mode": mode,
        "head_sha": head_sha,
        "base_sha": "0" * 40,
        "diff_sha256": "e" * 64,
        "issue_number": ISSUE_NUMBER,
        "criteria_digest": "b" * 64,
        "matrix_digest": "c" * 64,
        "result_digest": "d" * 64,
        "owner": "owner",
        "implementer": "implementer",
        "reviewer": "reviewer",
        "verdict": verdict,
        "rows": [
            {
                "category": f"C{number:02d}",
                "disposition": "reverified",
                "impact_reason": "checked",
                "evidence_paths": [".agents/rules/review-heuristics.md"],
                "ambiguous": False,
            }
            for number in range(1, 15)
        ],
        "findings": [],
        "notes": [],
    }


def _write_state(
    repo_root: Path,
    *,
    receipt: Mapping[str, object] | None = None,
) -> Path:
    state = {
        "issue_number": ISSUE_NUMBER,
        "worktree": str(repo_root),
        "owner": "owner",
        "implementer": "implementer",
        "commit_done": HEAD,
        "push_done": "feat/527",
        "push_head": HEAD,
        "pr_opened": {
            "repo": REPOSITORY,
            "number": PR_NUMBER,
            "url": PR_URL,
            "head_sha": HEAD,
        },
        "final_local_review": {
            "manifest": {"criteria_digest": "b" * 64},
            "receipt": dict(receipt or _receipt()),
        },
    }
    path = repo_root / ".process-state.json"
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _validator(
    state: Mapping[str, JsonValue],
    repo_root: Path,
    live_issue_body: str,
    expected_head: str,
    expected_issue_number: int,
) -> JsonObject:
    del repo_root
    if live_issue_body != ISSUE_BODY:
        raise ReviewReceiptError("issue digest mismatch")
    final_review = cast(
        JsonObject,
        state["final_local_review"],
    )
    receipt = cast(JsonObject, final_review["receipt"])
    if receipt.get("mode") != "full":
        raise ReviewReceiptError("delta receipt")
    if receipt.get("verdict") != "PASS":
        raise ReviewReceiptError("BLOCK receipt")
    if receipt.get("head_sha") != expected_head:
        raise ReviewReceiptError("stale receipt")
    if receipt.get("issue_number") != expected_issue_number:
        raise ReviewReceiptError("issue mismatch")
    return receipt


def _read_publication(path: Path) -> dict[str, object]:
    state = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    return cast(dict[str, object], state["publication"])


def _replace_state_value(
    path: Path,
    key: str,
    value: JsonValue,
) -> None:
    state = cast(
        JsonObject,
        json.loads(path.read_text(encoding="utf-8")),
    )
    state[key] = value
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _publish(
    runner: FakeCommandRunner,
    state_path: Path,
) -> None:
    publish_final_review(
        pr_number=PR_NUMBER,
        process_state_path=state_path,
        runner=runner,
        validator=_validator,
    )


def _expect_error(
    action: Callable[[], None],
    expected_text: str,
) -> None:
    try:
        action()
    except (PublicationError, ReviewReceiptError) as error:
        if expected_text not in str(error):
            raise AssertionError(
                f"expected error containing {expected_text!r}, got {error!r}"
            ) from error
        return
    raise AssertionError(f"expected error containing {expected_text!r}")


def test_first_run_and_exact_rerun() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        _publish(runner, state_path)
        assert runner.mutations == ["comment", "label", "status"]
        publication = _read_publication(state_path)
        assert publication["state"] == "published"
        assert publication["status_reused"] is False

        runner.mutations.clear()
        _publish(runner, state_path)
        assert runner.mutations == []
        publication = _read_publication(state_path)
        assert publication["state"] == "published"
        assert publication["status_reused"] is True

        original = runner.comments[0]
        runner.comments.append(
            {
                "id": 999,
                "html_url": f"{PR_URL}#issuecomment-999",
                "body": original["body"],
                "user": {"login": "trusted"},
            }
        )
        runner.mutations.clear()
        _publish(runner, state_path)
        assert runner.mutations == []
        assert _read_publication(state_path)["comment_id"] == 999

        runner.comments.append(
            {
                "id": 1000,
                "html_url": f"{PR_URL}#issuecomment-1000",
                "body": original["body"],
                "user": {"login": "untrusted"},
            }
        )
        runner.mutations.clear()
        _publish(runner, state_path)
        assert runner.mutations == []
        assert _read_publication(state_path)["comment_id"] == 999
        assert _read_publication(state_path)["comment_creator"] == "trusted"


def test_comment_requires_exact_body_and_trusted_creator() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        _publish(runner, state_path)
        original = runner.comments[0]
        exact_body = cast(str, original["body"])
        original["body"] = f"{exact_body}\n<!-- extra text -->"
        runner.comments.append(
            {
                "id": 999,
                "html_url": f"{PR_URL}#issuecomment-999",
                "body": exact_body,
                "user": {"login": "untrusted"},
            }
        )

        runner.mutations.clear()
        _publish(runner, state_path)

        assert runner.mutations == ["comment"]
        publication = _read_publication(state_path)
        assert publication["comment_id"] == 1000
        assert publication["comment_creator"] == "publisher"
        assert runner.comments[-1]["body"] == exact_body
        assert runner.comments[-1]["user"] == {"login": "publisher"}


def test_comment_permission_checks_fail_closed() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.actor = "untrusted"
        _expect_error(
            lambda: _publish(runner, state_path),
            "publisher actor role is not admin or maintain",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        _publish(runner, state_path)
        runner.permission_failures.add("publisher")
        runner.mutations.clear()
        _expect_error(lambda: _publish(runner, state_path), "permission unavailable")
        assert runner.mutations == []


def test_real_receipt_validator_integrates_with_publisher() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        policy_path = repo_root / ".agents/review-criteria-policy.json"
        policy_path.parent.mkdir(parents=True)
        policy_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "categories": list(CATEGORY_IDS),
                    "sources": [
                        ".agents/review-criteria-policy.json",
                        ".agents/rules.md",
                    ],
                }
            ),
            encoding="utf-8",
        )
        (repo_root / ".agents/rules.md").write_text("# rules\n", encoding="utf-8")
        for arguments in (
            ("init", "-b", "feat/527"),
            ("config", "user.name", "Publisher Contract"),
            ("config", "user.email", "publisher@example.invalid"),
            ("config", "core.hooksPath", "/dev/null"),
            ("add", "."),
            ("commit", "-m", "test: publisher base"),
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
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "update-ref",
                "refs/remotes/origin/develop",
                base_sha,
            ],
            check=True,
        )
        (repo_root / "changed.py").write_text("VALUE = 1\n", encoding="utf-8")
        for arguments in (
            ("add", "changed.py"),
            ("commit", "-m", "feat: publisher reviewed change"),
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
        manifest = build_criteria_manifest(repo_root, ISSUE_NUMBER, ISSUE_BODY)
        criteria_digest = cast(str, manifest["criteria_digest"])
        reviewer = "independent-reviewer"
        rows: list[JsonValue] = [
            {
                "category": category,
                "disposition": "reverified",
                "impact_reason": "current head inspected",
                "evidence_paths": ["changed.py"],
                "ambiguous": False,
            }
            for category in CATEGORY_IDS
        ]
        receipt: JsonObject = {
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
                [],
                [],
                head_sha=head,
                criteria_digest=criteria_digest,
                reviewer=reviewer,
            ),
            "owner": "owner",
            "implementer": "implementer",
            "reviewer": reviewer,
            "verdict": "PASS",
            "rows": rows,
            "findings": [],
            "notes": [],
            "blocker_count": 0,
        }
        state_path = _write_state(repo_root, receipt=receipt)
        state = cast(
            JsonObject,
            json.loads(state_path.read_text(encoding="utf-8")),
        )
        state["commit_done"] = head
        state["push_head"] = head
        pr_opened = cast(JsonObject, state["pr_opened"])
        pr_opened["head_sha"] = head
        state["final_review_delegate"] = {
            "head_sha": head,
            "criteria_digest": criteria_digest,
            "reviewer": reviewer,
        }
        state["final_local_review"] = {
            "manifest": manifest,
            "receipt": receipt,
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        runner = FakeCommandRunner(repo_root)
        runner.local_head = head
        runner.upstream_head = head
        runner.pr_head = head
        publish_final_review(
            pr_number=PR_NUMBER,
            process_state_path=state_path,
            runner=runner,
        )
        assert runner.mutations == ["comment", "label", "status"]
        assert _read_publication(state_path)["state"] == "published"


def test_partial_repairs_only_missing_surfaces() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        _publish(runner, state_path)

        runner.labels.clear()
        runner.statuses.clear()
        runner.mutations.clear()
        _publish(runner, state_path)
        assert runner.mutations == ["label", "status"]

        runner.comments.clear()
        runner.labels.clear()
        runner.mutations.clear()
        _publish(runner, state_path)
        assert runner.mutations == ["comment", "label"]


def test_preflight_failures_have_zero_mutations() -> None:
    cases = (
        ("delta receipt", _receipt(mode="delta"), None),
        ("only PASS", _receipt(verdict="BLOCK"), None),
        ("receipt head is stale", _receipt(head_sha="e" * 40), None),
        ("issue digest mismatch", _receipt(), "changed issue body\n"),
    )
    for expected, receipt, changed_body in cases:
        with TemporaryDirectory() as raw_directory:
            repo_root = Path(raw_directory).resolve()
            state_path = _write_state(repo_root, receipt=receipt)
            runner = FakeCommandRunner(repo_root)
            if changed_body is not None:
                runner.issue_body = changed_body
            _expect_error(lambda: _publish(runner, state_path), expected)
            assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.dirty = " M tracked.py\n"
        _expect_error(lambda: _publish(runner, state_path), "worktree is dirty")
        assert runner.mutations == []


def test_exact_head_and_pr_preflight_failures_have_zero_mutations() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.local_head = "e" * 40
        _expect_error(
            lambda: _publish(runner, state_path),
            "exact-head alignment",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.upstream_head = "e" * 40
        _expect_error(
            lambda: _publish(runner, state_path),
            "exact-head alignment",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        _replace_state_value(state_path, "push_head", "e" * 40)
        runner = FakeCommandRunner(repo_root)
        _expect_error(
            lambda: _publish(runner, state_path),
            "exact-head alignment",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        state = cast(
            JsonObject,
            json.loads(state_path.read_text(encoding="utf-8")),
        )
        stored_pr = cast(JsonObject, state["pr_opened"])
        stored_pr["repo"] = "wrong/repository"
        _replace_state_value(state_path, "pr_opened", stored_pr)
        runner = FakeCommandRunner(repo_root)
        _expect_error(
            lambda: _publish(runner, state_path),
            "stored PR repository mismatch",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.pr_head = "e" * 40
        _expect_error(
            lambda: _publish(runner, state_path),
            "live PR head mismatch",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.pr_draft = True
        _expect_error(
            lambda: _publish(runner, state_path),
            "live PR is draft",
        )
        assert runner.mutations == []

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.head_repo = "contributor/spakky-framework"
        _expect_error(
            lambda: _publish(runner, state_path),
            "not same-repository",
        )
        assert runner.mutations == []


def _status(
    identifier: int,
    state: str,
    creator: str,
) -> dict[str, object]:
    return {
        "id": identifier,
        "context": "ai-review",
        "state": state,
        "creator": {"login": creator},
    }


def test_status_trust_cases() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.statuses = [_status(210, "success", "trusted")]
        _publish(runner, state_path)
        assert runner.mutations == ["comment", "label"]
        assert _read_publication(state_path)["status_id"] == 210

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.statuses = [
            _status(210, "success", "trusted"),
            _status(220, "failure", "untrusted"),
        ]
        _publish(runner, state_path)
        assert runner.mutations == ["comment", "label", "status"]
        assert _read_publication(state_path)["status_id"] == 221

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.statuses = [_status(210, "failure", "trusted")]
        _expect_error(
            lambda: _publish(runner, state_path),
            "latest trusted ai-review status is not success",
        )
        assert runner.mutations == ["comment", "label"]
        assert _read_publication(state_path)["state"] == "incomplete"

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.statuses = [_status(210, "success", "trusted")]
        runner.permission_failures.add("trusted")
        _expect_error(lambda: _publish(runner, state_path), "permission unavailable")
        assert "status" not in runner.mutations

    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.roles["publisher"] = "write"
        _expect_error(
            lambda: _publish(runner, state_path),
            "publisher actor role is not admin or maintain",
        )
        assert "status" not in runner.mutations


def test_postflight_rejects_newer_overall_status() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.post_status_race = True
        _expect_error(
            lambda: _publish(runner, state_path),
            "postflight latest overall status",
        )
        assert runner.mutations == ["comment", "label", "status"]
        assert _read_publication(state_path)["state"] == "incomplete"


def test_postflight_rechecks_comment_creator_permission() -> None:
    with TemporaryDirectory() as raw_directory:
        repo_root = Path(raw_directory).resolve()
        state_path = _write_state(repo_root)
        runner = FakeCommandRunner(repo_root)
        runner.post_status_comment_demote = True
        _expect_error(
            lambda: _publish(runner, state_path),
            "postflight comment verification failed",
        )
        assert runner.mutations == ["comment", "label", "status"]
        assert _read_publication(state_path)["state"] == "incomplete"


def test_manual_mode_contract_preserves_fresh_three_verdict_path() -> None:
    skill = (
        SCRIPT_DIRECTORY.parents[3] / ".agents/skills/pr-review/SKILL.md"
    ).read_text(encoding="utf-8")
    start = "<!-- pr-review-mode-contract:start -->"
    end = "<!-- pr-review-mode-contract:end -->"
    assert skill.count(start) == 1
    assert skill.count(end) == 1
    mode_contract = skill.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]
    required_fragments = (
        "`/pr-review <PR>` (`--process-state` 없음)",
        "격리 subagent fresh review",
        "`AUTO_APPROVE` / `CHANGES_REQUESTED` / `HUMAN_REVIEW`",
        "`/pr-review <PR> --process-state <PATH>`",
        "기본 fresh review로 fallback하지 않는다",
    )
    for fragment in required_fragments:
        assert fragment in mode_contract, fragment

    no_argument = resolve_review_mode([])
    assert no_argument == {
        "mode": "manual-fresh",
        "pr_reference": None,
        "verdicts": list(MANUAL_VERDICTS),
    }
    explicit_manual = resolve_review_mode([str(PR_NUMBER)])
    assert explicit_manual == {
        "mode": "manual-fresh",
        "pr_reference": str(PR_NUMBER),
        "verdicts": ["AUTO_APPROVE", "CHANGES_REQUESTED", "HUMAN_REVIEW"],
    }
    receipt_route = resolve_review_mode(
        [str(PR_NUMBER), "--process-state", "/tmp/process-state.json"]
    )
    assert receipt_route == {
        "mode": "receipt-publication",
        "pr_reference": str(PR_NUMBER),
        "process_state": "/tmp/process-state.json",
    }
    assert "verdicts" not in receipt_route

    malformed_invocations = (
        ["--unknown"],
        [str(PR_NUMBER), "extra"],
        [str(PR_NUMBER), "--process-state"],
        [str(PR_NUMBER), "--process-state", " "],
        [str(PR_NUMBER), "--process-state", "/tmp/state", "extra"],
    )
    for invocation in malformed_invocations:
        try:
            resolve_review_mode(invocation)
        except ReviewModeError:
            pass
        else:
            raise AssertionError(f"malformed invocation passed: {invocation!r}")

    resolver = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIRECTORY / "resolve_review_mode.py"),
            str(PR_NUMBER),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert resolver.returncode == 0, resolver.stderr
    assert json.loads(resolver.stdout) == explicit_manual

    missing_state = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIRECTORY / "publish_final_review.py"),
            "--pr",
            str(PR_NUMBER),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_state.returncode == 2
    assert "--process-state" in missing_state.stderr


def main() -> int:
    _isolate_fixture_git_environment()
    tests = (
        test_first_run_and_exact_rerun,
        test_comment_requires_exact_body_and_trusted_creator,
        test_comment_permission_checks_fail_closed,
        test_real_receipt_validator_integrates_with_publisher,
        test_partial_repairs_only_missing_surfaces,
        test_preflight_failures_have_zero_mutations,
        test_exact_head_and_pr_preflight_failures_have_zero_mutations,
        test_status_trust_cases,
        test_postflight_rejects_newer_overall_status,
        test_postflight_rechecks_comment_creator_permission,
        test_manual_mode_contract_preserves_fresh_three_verdict_path,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("publish-final-review contract checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
