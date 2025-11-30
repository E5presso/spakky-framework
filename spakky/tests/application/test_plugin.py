from spakky.application.plugin import Plugin


def test_plugin_creation() -> None:
    """Test Plugin creation"""
    plugin = Plugin(name="test-plugin")
    assert plugin.name == "test-plugin"


def test_plugin_equality() -> None:
    """Test Plugin equality based on name"""
    plugin1 = Plugin(name="plugin-a")
    plugin2 = Plugin(name="plugin-a")
    plugin3 = Plugin(name="plugin-b")

    assert plugin1 == plugin2
    assert plugin1 != plugin3
    assert plugin1 != "not-a-plugin"


def test_plugin_hash() -> None:
    """Test Plugin hashing"""
    plugin1 = Plugin(name="plugin-a")
    plugin2 = Plugin(name="plugin-a")
    plugin3 = Plugin(name="plugin-b")

    assert hash(plugin1) == hash(plugin2)
    assert hash(plugin1) != hash(plugin3)

    # Can be used in sets/dicts
    plugin_set = {plugin1, plugin2, plugin3}
    assert len(plugin_set) == 2  # plugin1 and plugin2 are the same
