"""Wire-layout snapshot of the descriptors generated from controllers.

Field numbers are derived from field *names*, so renaming a pydantic field is
a wire-breaking change that no ``.proto`` artifact exists to catch. This
module renders the generated layout — message → field → number and type — as
deterministic JSON, and exposes it as the ``spakky-grpc-descriptor-snapshot``
command so a project can commit the snapshot and fail its own build when the
wire layout moves.
"""

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from google.protobuf.descriptor_pb2 import (
    DescriptorProto,
    FieldDescriptorProto,
    MethodDescriptorProto,
    ServiceDescriptorProto,
)
from pydantic import BaseModel
from spakky.core.common.importing import (
    is_package,
    list_classes,
    list_modules,
    resolve_module,
)

from spakky.plugins.grpc.error import NoControllerFoundError
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


class ProtoFieldSnapshot(BaseModel):
    """One protobuf field's wire-visible identity."""

    name: str
    number: int
    type: str
    label: str
    type_name: str
    """Fully-qualified type for message fields, empty for scalar fields."""

    proto3_optional: bool
    """Whether the field tracks explicit presence.

    Turning ``str`` into ``str | None`` keeps the number, the type and the label
    identical while changing what a peer decodes for an unset field between
    ``""`` and ``None``. Without this the snapshot diff would stay clean through
    that break.
    """


class ProtoMessageSnapshot(BaseModel):
    """One protobuf message with its fields ordered by field number."""

    name: str
    fields: list[ProtoFieldSnapshot]


class ProtoMethodSnapshot(BaseModel):
    """One RPC method with its request/response types and streaming shape."""

    name: str
    input_type: str
    output_type: str
    client_streaming: bool
    server_streaming: bool


class ProtoServiceSnapshot(BaseModel):
    """One gRPC service with its methods ordered by name."""

    name: str
    methods: list[ProtoMethodSnapshot]


class DescriptorSnapshot(BaseModel):
    """The full wire layout generated from a set of controllers."""

    services: list[ProtoServiceSnapshot]
    messages: list[ProtoMessageSnapshot]


def build_descriptor_snapshot(
    controller_types: Sequence[type],
) -> DescriptorSnapshot:
    """Render the wire layout generated from ``@GrpcController`` classes.

    Args:
        controller_types: Controller classes to describe.

    Returns:
        A snapshot whose services, messages and fields are in a stable order
        so two runs over the same declarations produce identical output.
    """
    file_descriptors = [
        build_file_descriptor(controller_type) for controller_type in controller_types
    ]
    # Controllers sharing a message type each carry their own copy of it, so the
    # messages are keyed by qualified name to emit one entry per wire type.
    messages = {
        f"{file_descriptor.package}.{message.name}": _message_snapshot(
            file_descriptor.package, message
        )
        for file_descriptor in file_descriptors
        for message in file_descriptor.message_type
    }
    return DescriptorSnapshot(
        services=sorted(
            (
                _service_snapshot(file_descriptor.package, service)
                for file_descriptor in file_descriptors
                for service in file_descriptor.service
            ),
            key=lambda service: service.name,
        ),
        messages=sorted(messages.values(), key=lambda message: message.name),
    )


def collect_controller_types(module_names: Sequence[str]) -> list[type]:
    """Import the named modules and collect every ``@GrpcController`` in them.

    Args:
        module_names: Dotted module or package paths to scan.

    Returns:
        The discovered controller classes, ordered by qualified name.

    Raises:
        NoControllerFoundError: If the named modules declare no controller. An
            empty snapshot would otherwise be committed as the baseline and
            every later comparison against it would pass, leaving the wire
            layout unguarded.
    """
    controller_types: set[type] = set()
    for module_name in module_names:
        for module in _expand_module(resolve_module(module_name)):
            controller_types |= list_classes(module, GrpcController.exists)
    if not controller_types:
        raise NoControllerFoundError(tuple(module_names))
    return sorted(controller_types, key=lambda controller: controller.__qualname__)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the descriptor snapshot for the modules named on the command line.

    Args:
        argv: Command-line arguments. ``None`` reads ``sys.argv``.

    Returns:
        The process exit status, which is always success once the modules
        imported and the descriptors built.
    """
    parser = ArgumentParser(
        prog="spakky-grpc-descriptor-snapshot",
        description=(
            "Dump the protobuf wire layout generated from @GrpcController "
            "classes so it can be committed and diffed in CI."
        ),
    )
    parser.add_argument(
        "modules",
        nargs="+",
        metavar="MODULE",
        help="Dotted module or package path containing @GrpcController classes.",
    )
    arguments = parser.parse_args(argv)
    # A console script starts with the installation directory on ``sys.path`` and not
    # the working directory, so without this the project the command is invoked from
    # would not be importable by name.
    sys.path.insert(0, str(Path.cwd()))
    snapshot = build_descriptor_snapshot(collect_controller_types(arguments.modules))
    print(snapshot.model_dump_json(indent=2))
    return 0


def _expand_module(module: ModuleType) -> set[ModuleType]:
    """Return *module* plus every submodule when it is a package."""
    if is_package(module):
        return {module} | list_modules(module)
    return {module}


def _service_snapshot(
    package: str, service: ServiceDescriptorProto
) -> ProtoServiceSnapshot:
    """Render one service descriptor into its snapshot form."""
    return ProtoServiceSnapshot(
        name=f"{package}.{service.name}",
        methods=sorted(
            (_method_snapshot(method) for method in service.method),
            key=lambda method: method.name,
        ),
    )


def _method_snapshot(method: MethodDescriptorProto) -> ProtoMethodSnapshot:
    """Render one method descriptor into its snapshot form."""
    return ProtoMethodSnapshot(
        name=method.name,
        input_type=method.input_type,
        output_type=method.output_type,
        client_streaming=method.client_streaming,
        server_streaming=method.server_streaming,
    )


def _message_snapshot(package: str, message: DescriptorProto) -> ProtoMessageSnapshot:
    """Render one message descriptor into its snapshot form."""
    return ProtoMessageSnapshot(
        name=f"{package}.{message.name}",
        fields=sorted(
            (_field_snapshot(field) for field in message.field),
            key=lambda field: field.number,
        ),
    )


def _field_snapshot(field: FieldDescriptorProto) -> ProtoFieldSnapshot:
    """Render one field descriptor into its snapshot form."""
    return ProtoFieldSnapshot(
        name=field.name,
        number=field.number,
        type=FieldDescriptorProto.Type.Name(field.type),
        label=FieldDescriptorProto.Label.Name(field.label),
        type_name=field.type_name,
        proto3_optional=field.proto3_optional,
    )
