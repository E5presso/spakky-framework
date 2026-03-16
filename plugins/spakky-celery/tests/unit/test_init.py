"""Tests for CeleryPlugin __init__."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.celery import PLUGIN_NAME


def test_plugin_name_is_plugin_instance() -> None:
    """PLUGIN_NAME이 Plugin 인스턴스인지 검증한다."""
    assert isinstance(PLUGIN_NAME, Plugin)


def test_plugin_name_value() -> None:
    """PLUGIN_NAME의 name이 'spakky-celery'인지 검증한다."""
    assert PLUGIN_NAME.name == "spakky-celery"
