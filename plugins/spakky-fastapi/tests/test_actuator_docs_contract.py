"""Documentation contract tests for FastAPI actuator exposure."""

from pathlib import Path


def test_fastapi_actuator_docs_expect_security_hardening_warning() -> None:
    """Docs must warn that FastAPI actuator routes need explicit protection."""
    guide = Path("docs/guides/actuator.md").read_text(encoding="utf-8")
    readme = Path("plugins/spakky-fastapi/README.md").read_text(encoding="utf-8")

    for doc in (guide, readme):
        assert "unauthenticated by default" in doc
        assert "internal networking" in doc
        assert "reverse-proxy allowlist" in doc
        assert "ActuatorConfig(include_details=False)" in doc
