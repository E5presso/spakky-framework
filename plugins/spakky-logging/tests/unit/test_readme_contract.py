"""README examples should match the public logging configuration API."""

from pathlib import Path


README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_uses_environment_variables_for_logging_config() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "SPAKKY_LOGGING__LEVEL" in readme
    assert "SPAKKY_LOGGING__FORMAT" in readme
    assert "SPAKKY_LOGGING__MASK_KEYS" in readme
    assert "SPAKKY_LOGGING__SLOW_THRESHOLD_MS" in readme


def test_readme_does_not_show_keyword_logging_config_constructor() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "LoggingConfig(" not in readme
    assert "mask_keys=frozenset" not in readme
