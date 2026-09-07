"""Regression tests for project versus installed-provider harness ownership."""

from __future__ import annotations

import base64
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_python_harness.py"
SPEC = spec_from_file_location("validate_python_harness", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / ".agents" / "skills").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    return root


def _owned_state(root: Path, relative: str, content: bytes) -> None:
    state = {
        "schema": 1,
        "distribution": "a" * 64,
        "owned": {
            relative: {
                "original": None,
                "installed": {
                    "kind": "file",
                    "data": base64.b64encode(content).decode(),
                    "mode": 0o644,
                },
            }
        },
    }
    path = root / ".neurath" / "install.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(state))


def test_verified_provider_file_requires_exact_owned_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    relative = ".agents/skills/neurath-watch-pr/scripts/provider.py"
    content = b"try:\n    pass\nexcept ValueError, TypeError:\n    pass\n"
    provider = root / relative
    provider.parent.mkdir(parents=True)
    provider.write_bytes(content)
    _owned_state(root, relative, content)
    monkeypatch.setattr(
        VALIDATOR,
        "_neurath_installation_integrity_passes",
        lambda _root: True,
    )

    verified = VALIDATOR.verified_neurath_owned_python_files(root)

    assert provider.resolve() in verified
    provider.write_bytes(content + b"# locally modified\n")
    assert provider.resolve() not in VALIDATOR.verified_neurath_owned_python_files(
        root
    )


def test_validate_skips_exact_provider_snapshot_but_not_prefix_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    relative = ".agents/skills/neurath-watch-pr/scripts/provider.py"
    content = b"try:\n    pass\nexcept ValueError, TypeError:\n    pass\n"
    provider = root / relative
    provider.parent.mkdir(parents=True)
    provider.write_bytes(content)
    _owned_state(root, relative, content)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        VALIDATOR,
        "_neurath_installation_integrity_passes",
        lambda _root: True,
    )

    assert VALIDATOR.validate([root / ".agents"]) == []

    (root / ".neurath" / "install.json").unlink()
    violations = VALIDATOR.validate([root / ".agents"])
    assert len(violations) == 1
    assert "Python syntax is invalid" in violations[0].message


def test_unowned_prefixed_skill_keeps_project_protocol_policy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    source = root / ".agents/skills/neurath-user/scripts/contract.py"
    source.parent.mkdir(parents=True)
    source.write_text("from typing import Protocol\n")
    monkeypatch.chdir(root)

    violations = VALIDATOR.validate([root / ".agents"])

    assert len(violations) == 1
    assert "Protocol import is forbidden" in violations[0].message


def test_invalid_install_state_cannot_exclude_provider_named_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    provider = root / ".agents/skills/neurath-watch-pr/scripts/provider.py"
    provider.parent.mkdir(parents=True)
    provider.write_text("from typing import Protocol\n")
    state = root / ".neurath/install.json"
    state.parent.mkdir()

    state.write_text("{invalid")
    assert VALIDATOR.verified_neurath_owned_python_files(root) == set()

    _owned_state(
        root,
        ".agents/skills/neurath-watch-pr/scripts/provider.py",
        provider.read_bytes(),
    )
    payload = json.loads(state.read_text())
    payload["distribution"] = "not-a-distribution"
    state.write_text(json.dumps(payload))
    assert VALIDATOR.verified_neurath_owned_python_files(root) == set()

    payload["distribution"] = "a" * 64
    state.write_text(json.dumps(payload))
    monkeypatch.setattr(
        VALIDATOR,
        "_neurath_installation_integrity_passes",
        lambda _root: False,
    )
    assert VALIDATOR.verified_neurath_owned_python_files(root) == set()


def test_owned_snapshot_cannot_escape_skill_tree_or_follow_symlinks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    outside = root / "outside.py"
    outside.write_text("from typing import Protocol\n")
    linked = root / ".agents/skills/neurath-watch-pr/scripts/provider.py"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(outside)
    state = {
        "schema": 1,
        "distribution": "a" * 64,
        "owned": {
            ".agents/skills/neurath-watch-pr/scripts/provider.py": {
                "installed": {
                    "kind": "file",
                    "data": base64.b64encode(outside.read_bytes()).decode(),
                    "mode": 0o644,
                }
            },
            "outside.py": {
                "installed": {
                    "kind": "file",
                    "data": base64.b64encode(outside.read_bytes()).decode(),
                    "mode": 0o644,
                }
            },
            ".agents/skills/../../outside.py": {
                "installed": {
                    "kind": "file",
                    "data": base64.b64encode(outside.read_bytes()).decode(),
                    "mode": 0o644,
                }
            },
        },
    }
    state_path = root / ".neurath/install.json"
    state_path.parent.mkdir()
    state_path.write_text(json.dumps(state))
    monkeypatch.setattr(
        VALIDATOR,
        "_neurath_installation_integrity_passes",
        lambda _root: True,
    )

    assert VALIDATOR.verified_neurath_owned_python_files(root) == set()


def test_owned_snapshot_cannot_follow_ancestor_directory_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    actual = root / "core/pkg/src"
    actual.mkdir(parents=True)
    source = actual / "contract.py"
    source.write_text("from typing import Protocol\n")
    alias = root / ".agents/skills/neurath-link"
    alias.symlink_to(actual, target_is_directory=True)
    relative = ".agents/skills/neurath-link/contract.py"
    _owned_state(root, relative, source.read_bytes())
    monkeypatch.setattr(
        VALIDATOR,
        "_neurath_installation_integrity_passes",
        lambda _root: True,
    )

    assert VALIDATOR.verified_neurath_owned_python_files(root) == set()


def test_validator_always_uses_python_312_grammar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _workspace(tmp_path)
    source = root / ".agents/skills/user/scripts/provider.py"
    source.parent.mkdir(parents=True)
    source.write_text("try:\n    pass\nexcept ValueError, TypeError:\n    pass\n")
    monkeypatch.chdir(root)

    violations = VALIDATOR.validate([root / ".agents"])

    assert len(violations) == 1
    assert "Python syntax is invalid" in violations[0].message
