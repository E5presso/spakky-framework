"""README contract tests for Typer setup snippets."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_readme_setup_expect_manual_typer_pod_registration() -> None:
    """README must show that applications register the Typer Pod."""
    readme = (REPO_ROOT / "plugins/spakky-typer/README.md").read_text(encoding="utf-8")

    assert '@Pod(name="cli")' in readme
    assert "def get_cli() -> Typer:" in readme
    assert ".add(get_cli)" in readme
    assert "Typer` 인스턴스 자체는 애플리케이션에서 Pod로 등록해야 합니다" in readme
