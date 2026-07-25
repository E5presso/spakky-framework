"""Unit tests for the descriptor snapshot rendered for wire-layout diffing."""

from json import loads

import pytest
from pydantic import BaseModel
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.error import NoControllerFoundError
from spakky.plugins.grpc.schema.field_number import assign_field_numbers
from spakky.plugins.grpc.schema.snapshot import (
    build_descriptor_snapshot,
    collect_controller_types,
    main,
)
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

from tests.unit.conftest import GreeterController, HelloRequest

CONTROLLER_MODULE = "tests.unit.conftest"
SERVICE_NAME = "test.v1.GreeterController"
MODULE_WITHOUT_CONTROLLER = "json"


class PresenceRequired(BaseModel):
    """Message whose single field has no explicit presence."""

    nickname: str


class PresenceOptional(BaseModel):
    """Same message with the field made optional, keeping name and type."""

    nickname: str | None


@GrpcController(package="presence.v1", service_name="Required")
class PresenceRequiredController:
    """Controller exposing the message without explicit presence."""

    @rpc()
    async def echo(self, request: PresenceRequired) -> PresenceRequired:
        """Echo the message back."""
        return request


@GrpcController(package="presence.v1", service_name="Optional")
class PresenceOptionalController:
    """Controller exposing the message with explicit presence."""

    @rpc()
    async def echo(self, request: PresenceOptional) -> PresenceOptional:
        """Echo the message back."""
        return request


def test_build_descriptor_snapshot_expect_field_numbers_from_declarations() -> None:
    """Each message field should report the number the descriptor builder assigns."""
    snapshot = build_descriptor_snapshot([GreeterController])

    request = next(
        message
        for message in snapshot.messages
        if message.name.endswith("HelloRequest")
    )
    assert {
        field.name: field.number for field in request.fields
    } == assign_field_numbers(HelloRequest)


def test_build_descriptor_snapshot_expect_scalar_field_type_names() -> None:
    """Scalar fields should carry their protobuf type and label names."""
    snapshot = build_descriptor_snapshot([GreeterController])

    reply = next(
        message for message in snapshot.messages if message.name.endswith("HelloReply")
    )
    assert [(field.type, field.label) for field in reply.fields] == [
        ("TYPE_STRING", "LABEL_OPTIONAL")
    ]


def test_build_descriptor_snapshot_expect_service_methods() -> None:
    """Services should list their RPC methods with the streaming shape."""
    snapshot = build_descriptor_snapshot([GreeterController])

    service = next(
        service for service in snapshot.services if service.name == SERVICE_NAME
    )
    method = next(method for method in service.methods if method.name == "say_hello")
    assert (method.client_streaming, method.server_streaming) == (False, False)
    assert method.input_type == ".test.v1.HelloRequest"


def test_build_descriptor_snapshot_expect_presence_change_detected() -> None:
    """Making a field optional must change the snapshot even though its number does not.

    Number, protobuf type and label are all identical between ``str`` and
    ``str | None``, but a peer decodes an unset value as ``""`` in one case and
    ``None`` in the other — the snapshot has to move for the CI gate to fire.
    """
    required = build_descriptor_snapshot([PresenceRequiredController])
    optional = build_descriptor_snapshot([PresenceOptionalController])

    required_field = required.messages[0].fields[0]
    optional_field = optional.messages[0].fields[0]
    assert (required_field.number, required_field.label) == (
        optional_field.number,
        optional_field.label,
    )
    assert (required_field.proto3_optional, optional_field.proto3_optional) == (
        False,
        True,
    )


def test_build_descriptor_snapshot_expect_stable_ordering() -> None:
    """Two runs over the same declarations must produce byte-identical output."""
    first = build_descriptor_snapshot([GreeterController])
    second = build_descriptor_snapshot([GreeterController])

    assert first.model_dump_json() == second.model_dump_json()


def test_build_descriptor_snapshot_with_shared_message_expect_single_entry() -> None:
    """A message reached from two controllers should appear once in the snapshot."""
    snapshot = build_descriptor_snapshot([GreeterController, GreeterController])

    message_names = [message.name for message in snapshot.messages]
    assert len(message_names) == len(set(message_names))


def test_collect_controller_types_from_module_expect_declared_controllers() -> None:
    """Scanning a plain module should find the controllers declared in it."""
    assert GreeterController in collect_controller_types([CONTROLLER_MODULE])


def test_collect_controller_types_from_package_expect_declared_controllers() -> None:
    """Scanning a package should reach controllers declared in its submodules."""
    assert GreeterController in collect_controller_types(["tests.unit"])


def test_collect_controller_types_without_controller_expect_error() -> None:
    """A scan that finds nothing must fail instead of yielding an empty baseline.

    An empty snapshot committed as the baseline compares clean forever, so a
    mistyped module path would silently disarm the CI gate.
    """
    with pytest.raises(NoControllerFoundError):
        collect_controller_types([MODULE_WITHOUT_CONTROLLER])


def test_main_expect_snapshot_printed_as_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command should print the snapshot as JSON and report success."""
    exit_status = main([CONTROLLER_MODULE])

    printed = loads(capsys.readouterr().out)
    assert exit_status == 0
    assert SERVICE_NAME in {service["name"] for service in printed["services"]}
