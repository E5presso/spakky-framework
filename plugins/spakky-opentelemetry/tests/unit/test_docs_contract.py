"""Documentation examples should match LogContextBridge behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_docs_use_log_context_bridge_instance_sync() -> None:
    docs = [
        _read("plugins/spakky-opentelemetry/README.md"),
        _read("docs/guides/opentelemetry.md"),
    ]

    for text in docs:
        assert "bridge.sync()" in text
        assert "LogContextBridge.sync()" not in text


def test_logging_guide_does_not_claim_automatic_bridge_sync() -> None:
    text = _read("docs/guides/logging.md")

    assert "bridge.sync()" in text
    assert "자동 동기화" not in text
