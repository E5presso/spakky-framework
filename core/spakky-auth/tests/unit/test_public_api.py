from spakky.auth import PLUGIN_NAME
from spakky.auth.main import initialize
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_plugin_name_identifies_auth_package() -> None:
    assert PLUGIN_NAME.name == "spakky-auth"


def test_initialize_is_registration_only_for_package_skeleton() -> None:
    app = SpakkyApplication(ApplicationContext())

    assert initialize(app) is None
