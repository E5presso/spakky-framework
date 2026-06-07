"""README contract tests for FastAPI setup snippets."""

from pathlib import Path


def test_readme_setup_expect_manual_fastapi_pod_registration() -> None:
    """README must show that applications register the FastAPI Pod."""
    readme = Path("plugins/spakky-fastapi/README.md").read_text(encoding="utf-8")

    assert "@Pod(name=\"api\")" in readme
    assert "def get_api() -> FastAPI:" in readme
    assert ".add(get_api)" in readme
    assert "자동 등록합니다" not in readme
