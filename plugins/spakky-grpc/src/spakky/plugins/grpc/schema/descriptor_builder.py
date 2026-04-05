"""Dataclass to ``FileDescriptorProto`` builder.

Converts Python dataclasses annotated with :class:`ProtoField` and
methods annotated with :class:`Rpc` into a
:class:`~google.protobuf.descriptor_pb2.FileDescriptorProto` suitable
for registration with a :class:`~google.protobuf.descriptor_pool.DescriptorPool`.
"""

from dataclasses import fields as dc_fields
from typing import Annotated, get_args, get_origin, get_type_hints

from google.protobuf.descriptor_pb2 import (
    DescriptorProto,
    FieldDescriptorProto,
    FileDescriptorProto,
    MethodDescriptorProto,
    ServiceDescriptorProto,
)

from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import Rpc, RpcMethodType
from spakky.plugins.grpc.error import (
    DuplicateFieldNumberError,
    MissingProtoFieldError,
)
from spakky.plugins.grpc.schema.type_map import (
    is_message_type,
    is_optional,
    is_repeated,
    resolve_proto_type,
    unwrap_optional,
    unwrap_repeated,
)


def _extract_proto_field(
    dataclass_type: type,
    field_name: str,
    type_hint: type,
) -> ProtoField:
    """Extract the ``ProtoField`` annotation from an ``Annotated`` type hint.

    Args:
        dataclass_type: The dataclass owning the field.
        field_name: The name of the field.
        type_hint: The full type hint (expected to be ``Annotated[T, ProtoField(...)]``).

    Returns:
        The ProtoField annotation.

    Raises:
        MissingProtoFieldError: If no ProtoField is found in the annotation.
    """
    if get_origin(type_hint) is Annotated:
        for metadata in get_args(type_hint)[1:]:
            if isinstance(metadata, ProtoField):
                return metadata
    raise MissingProtoFieldError(dataclass_type, field_name)


def _resolve_inner_type(type_hint: type) -> type:
    """Unwrap ``Annotated``, ``Optional``, and ``list`` to get the core type.

    Args:
        type_hint: The raw type hint.

    Returns:
        The innermost concrete type.
    """
    if get_origin(type_hint) is Annotated:
        type_hint = get_args(type_hint)[0]
    if is_optional(type_hint):
        type_hint = unwrap_optional(type_hint)
    if is_repeated(type_hint):
        type_hint = unwrap_repeated(type_hint)
    return type_hint


def _build_field_descriptor(
    dataclass_type: type,
    field_name: str,
    type_hint: type,
    package: str,
) -> FieldDescriptorProto:
    """Build a single ``FieldDescriptorProto`` from a dataclass field.

    Args:
        dataclass_type: The owning dataclass.
        field_name: The field name.
        type_hint: The full Annotated type hint.
        package: The protobuf package name.

    Returns:
        A configured FieldDescriptorProto.
    """
    proto_field = _extract_proto_field(dataclass_type, field_name, type_hint)

    raw_type = (
        get_args(type_hint)[0] if get_origin(type_hint) is Annotated else type_hint
    )

    optional = is_optional(raw_type)
    repeated = is_repeated(raw_type)
    inner = _resolve_inner_type(type_hint)

    field_desc = FieldDescriptorProto()
    field_desc.name = field_name
    field_desc.number = proto_field.number
    field_desc.type = resolve_proto_type(inner)

    if repeated:
        field_desc.label = FieldDescriptorProto.LABEL_REPEATED
    else:
        field_desc.label = FieldDescriptorProto.LABEL_OPTIONAL

    if is_message_type(inner):
        field_desc.type_name = f".{package}.{inner.__name__}"

    if optional and not repeated:
        field_desc.proto3_optional = True

    return field_desc


def build_message_descriptor(
    dataclass_type: type,
    package: str,
) -> tuple[DescriptorProto, list[type]]:
    """Build a ``DescriptorProto`` from a dataclass.

    Args:
        dataclass_type: The dataclass to convert.
        package: The protobuf package name.

    Returns:
        A tuple of (DescriptorProto, list of referenced message types).

    Raises:
        DuplicateFieldNumberError: If two fields share the same number.
        MissingProtoFieldError: If a field lacks a ProtoField annotation.
    """
    hints = get_type_hints(dataclass_type, include_extras=True)
    msg_desc = DescriptorProto()
    msg_desc.name = dataclass_type.__name__

    seen_numbers: set[int] = set()
    referenced_types: list[type] = []
    oneof_index = 0

    for dc_field in dc_fields(dataclass_type):
        type_hint = hints[dc_field.name]
        field_desc = _build_field_descriptor(
            dataclass_type, dc_field.name, type_hint, package
        )

        if field_desc.number in seen_numbers:
            raise DuplicateFieldNumberError(dataclass_type, field_desc.number)
        seen_numbers.add(field_desc.number)

        if field_desc.proto3_optional:
            oneof = msg_desc.oneof_decl.add()
            oneof.name = f"_{dc_field.name}"
            field_desc.oneof_index = oneof_index
            oneof_index += 1

        msg_desc.field.append(field_desc)

        inner = _resolve_inner_type(type_hint)
        if is_message_type(inner) and inner is not dataclass_type:
            referenced_types.append(inner)

    return msg_desc, referenced_types


def _build_method_descriptor(
    method_name: str,
    rpc_annotation: Rpc,
    package: str,
) -> MethodDescriptorProto:
    """Build a ``MethodDescriptorProto`` from an ``@rpc`` annotation.

    Args:
        method_name: The method name.
        rpc_annotation: The Rpc annotation.
        package: The protobuf package name.

    Returns:
        A configured MethodDescriptorProto.
    """
    method_desc = MethodDescriptorProto()
    method_desc.name = method_name

    request_type = rpc_annotation.request_type
    response_type = rpc_annotation.response_type
    if request_type is not None:
        method_desc.input_type = f".{package}.{request_type.__name__}"
    if response_type is not None:
        method_desc.output_type = f".{package}.{response_type.__name__}"

    method_desc.client_streaming = rpc_annotation.method_type in (
        RpcMethodType.CLIENT_STREAMING,
        RpcMethodType.BIDI_STREAMING,
    )
    method_desc.server_streaming = rpc_annotation.method_type in (
        RpcMethodType.SERVER_STREAMING,
        RpcMethodType.BIDI_STREAMING,
    )

    return method_desc


def build_service_descriptor(
    controller_type: type,
    service_name: str,
    package: str,
) -> tuple[ServiceDescriptorProto, list[type]]:
    """Build a ``ServiceDescriptorProto`` from a ``@GrpcController`` class.

    Scans the class for methods annotated with ``@rpc`` and builds
    method descriptors for each.

    Args:
        controller_type: The controller class.
        service_name: The gRPC service name.
        package: The protobuf package name.

    Returns:
        A tuple of (ServiceDescriptorProto, list of message types referenced).
    """
    service_desc = ServiceDescriptorProto()
    service_desc.name = service_name

    referenced_types: list[type] = []

    for attr_name in dir(controller_type):
        attr = getattr(controller_type, attr_name, None)
        if attr is None or not callable(attr):
            continue
        if not Rpc.exists(attr):
            continue

        rpc_annotation = Rpc.get(attr)
        method_desc = _build_method_descriptor(attr_name, rpc_annotation, package)
        service_desc.method.append(method_desc)

        if rpc_annotation.request_type is not None:
            referenced_types.append(rpc_annotation.request_type)
        if rpc_annotation.response_type is not None:
            referenced_types.append(rpc_annotation.response_type)

    return service_desc, referenced_types


def build_file_descriptor(
    package: str,
    service_name: str,
    controller_type: type,
) -> FileDescriptorProto:
    """Build a complete ``FileDescriptorProto`` for a gRPC controller.

    Generates message descriptors for all referenced types and a service
    descriptor for the controller.

    Args:
        package: The protobuf package name.
        service_name: The gRPC service name.
        controller_type: The controller class.

    Returns:
        A fully-populated FileDescriptorProto.
    """
    file_desc = FileDescriptorProto()
    file_desc.name = f"{package.replace('.', '/')}/{service_name}.proto"
    file_desc.package = package
    file_desc.syntax = "proto3"

    service_desc, service_types = build_service_descriptor(
        controller_type, service_name, package
    )

    registered_messages: set[str] = set()
    pending_types: list[type] = list(service_types)

    while pending_types:
        msg_type = pending_types.pop(0)
        if msg_type.__name__ in registered_messages:
            continue
        registered_messages.add(msg_type.__name__)

        msg_desc, nested_types = build_message_descriptor(msg_type, package)
        file_desc.message_type.append(msg_desc)
        pending_types.extend(nested_types)

    file_desc.service.append(service_desc)

    return file_desc
