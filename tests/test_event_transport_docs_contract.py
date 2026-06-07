"""Messaging guide setup examples should load the event core plugin."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_rabbitmq_guide_loads_event_and_transport_plugins() -> None:
    text = _read("docs/guides/rabbitmq.md")

    assert "import spakky.event" in text
    assert "spakky.event.PLUGIN_NAME" in text
    assert "spakky.plugins.rabbitmq.PLUGIN_NAME" in text
    assert "IAsyncEventPublisher" in text
    assert "`spakky[event-driven]` includes" in text


def test_kafka_guide_loads_event_and_transport_plugins() -> None:
    text = _read("docs/guides/kafka.md")

    assert "import spakky.event" in text
    assert "spakky.event.PLUGIN_NAME" in text
    assert "spakky.plugins.kafka.PLUGIN_NAME" in text
    assert "IAsyncEventPublisher" in text
    assert "`spakky[event-driven]` includes" in text
