"""README contract tests for Typer setup snippets."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_readme_setup_explains_default_typer_app() -> None:
    """README must show that the plugin provides the default Typer Pod."""
    readme = (REPO_ROOT / "plugins/spakky-typer/README.md").read_text(encoding="utf-8")

    assert "`spakky-typer`는 기본 `Typer` 앱을 Pod로 제공합니다" in readme
    assert ".load_plugins(include={spakky.plugins.typer.PLUGIN_NAME})" in readme
    assert ".add(get_cli)" not in readme
