from spakky.core.application.plugin import Plugin


def test_plugin_creation() -> None:
    """Plugin 생성이 정상적으로 동작함을 검증한다."""
    plugin = Plugin(name="test-plugin")
    assert plugin.name == "test-plugin"


def test_plugin_equality() -> None:
    """이름 기반으로 Plugin 동등성이 판단됨을 검증한다."""
    plugin1 = Plugin(name="plugin-a")
    plugin2 = Plugin(name="plugin-a")
    plugin3 = Plugin(name="plugin-b")

    assert plugin1 == plugin2
    assert plugin1 != plugin3
    assert plugin1 != "not-a-plugin"


def test_plugin_hash() -> None:
    """Plugin 해싱이 정상적으로 동작함을 검증한다."""
    plugin1 = Plugin(name="plugin-a")
    plugin2 = Plugin(name="plugin-a")
    plugin3 = Plugin(name="plugin-b")

    assert hash(plugin1) == hash(plugin2)
    assert hash(plugin1) != hash(plugin3)

    # Can be used in sets/dicts
    plugin_set = {plugin1, plugin2, plugin3}
    assert len(plugin_set) == 2  # plugin1 and plugin2 are the same
