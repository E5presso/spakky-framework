"""README contract tests for FastAPI setup snippets."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_readme_setup_explains_default_fastapi_app() -> None:
    """README must show the plugin-provided FastAPI app path."""
    readme = (REPO_ROOT / "plugins/spakky-fastapi/README.md").read_text(
        encoding="utf-8"
    )

    assert "`spakky-fastapi`는 기본 `FastAPI` 앱을 Pod로 제공합니다." in readme
    assert "SPAKKY_FASTAPI_TITLE" in readme
    assert ".add(custom_fastapi)" in readme
    assert "Pod로 직접 등록해야 합니다" not in readme
