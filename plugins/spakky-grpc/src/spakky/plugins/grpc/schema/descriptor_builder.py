"""Pydantic BaseModel to protobuf FileDescriptorProto builder.

Converts pydantic ``BaseModel`` subclasses with ``ProtoField`` metadata
and ``@rpc``-decorated controller methods into protobuf
``FileDescriptorProto`` instances.
"""

from inspect import getmembers, isfunction
from typing import cast

from google.protobuf.descriptor_pb2 import (
    DescriptorProto,
    FieldDescriptorProto,
    FileDescriptorProto,
    MethodDescriptorProto,
    OneofDescriptorProto,
    ServiceDescriptorProto,
)
from pydantic import BaseModel
from spakky.plugins.grpc.decorators.rpc import Rpc
from spakky.plugins.grpc.schema.type_map import (
    extract_proto_field,
    resolve_type,
)
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


def build_message_descriptor(
    model_type: type[BaseModel],
    collected: dict[str, DescriptorProto] | None = None,
) -> tuple[DescriptorProto, dict[str, DescriptorProto]]:
    """Build a ``DescriptorProto`` from a pydantic ``BaseModel`` subclass.

    Recursively processes nested ``BaseModel`` fields into nested message
    descriptors.

    Args:
        model_type: The ``BaseModel`` subclass to convert.
        collected: Accumulator for all message descriptors encountered
            during recursive processing. Used internally.

    Returns:
        A tuple of (root ``DescriptorProto``, dict of all collected
        descriptors).
    """
    if collected is None:
        collected = {}

    name = model_type.__name__
    if name in collected:
        return collected[name], collected

    descriptor = DescriptorProto(name=name)
    collected[name] = descriptor

    for field_name, field_info in model_type.model_fields.items():
        resolved = resolve_type(field_info.annotation)
        proto_field = extract_proto_field(model_type, field_name)

        field_desc = FieldDescriptorProto(
            name=field_name,
            number=proto_field.number,
            type=cast(FieldDescriptorProto.Type.ValueType, resolved.proto_type),
        )

        if resolved.is_repeated:
            field_desc.label = FieldDescriptorProto.LABEL_REPEATED
        elif resolved.is_optional:
            field_desc.label = FieldDescriptorProto.LABEL_OPTIONAL
            field_desc.proto3_optional = True
            oneof_index = len(descriptor.oneof_decl)
            descriptor.oneof_decl.append(OneofDescriptorProto(name=f"__{field_name}"))
            field_desc.oneof_index = oneof_index
        else:
            field_desc.label = FieldDescriptorProto.LABEL_OPTIONAL

        if resolved.is_message and resolved.message_type is not None:
            field_desc.type_name = resolved.message_type.__name__
            build_message_descriptor(resolved.message_type, collected)

        descriptor.field.append(field_desc)

    return descriptor, collected


def build_service_descriptor(
    controller_type: type,
    package: str,
    service_name: str,
    collected: dict[str, DescriptorProto],
) -> ServiceDescriptorProto:
    """Build a ``ServiceDescriptorProto`` from an ``@GrpcController`` class.

    Inspects all ``@rpc``-decorated methods on the controller and generates
    method descriptors with fully-qualified type names.

    Args:
        controller_type: The controller class to inspect.
        package: The protobuf package name.
        service_name: The gRPC service name.
        collected: Accumulator for message descriptors found in method
            signatures.

    Returns:
        A ``ServiceDescriptorProto`` for the controller.
    """
    service = ServiceDescriptorProto(name=service_name)

    for method_name, method in getmembers(controller_type, predicate=isfunction):
        if not Rpc.exists(method):
            continue

        rpc_annotation = Rpc.get(method)
        request_type = rpc_annotation.request_type
        response_type = rpc_annotation.response_type

        if request_type is not None:
            build_message_descriptor(request_type, collected)
            input_type = f".{package}.{request_type.__name__}"
        else:
            input_type = ""

        if response_type is not None:
            build_message_descriptor(response_type, collected)
            output_type = f".{package}.{response_type.__name__}"
        else:
            output_type = ""

        method_desc = MethodDescriptorProto(
            name=method_name,
            input_type=input_type,
            output_type=output_type,
        )

        service.method.append(method_desc)

    return service


def build_file_descriptor(controller_type: type) -> FileDescriptorProto:
    """Build a complete ``FileDescriptorProto`` from an ``@GrpcController`` class.

    Generates all message descriptors referenced by ``@rpc`` methods and
    the service descriptor, packaged into a single ``FileDescriptorProto``.

    Args:
        controller_type: The ``@GrpcController``-decorated class.

    Returns:
        A ``FileDescriptorProto`` ready for ``descriptor_pool`` registration.
    """
    annotation = GrpcController.get(controller_type)
    package = annotation.package
    service_name = annotation.service_name or controller_type.__name__

    file_name = f"{package.replace('.', '/')}/{service_name}.proto"

    collected: dict[str, DescriptorProto] = {}
    service = build_service_descriptor(
        controller_type, package, service_name, collected
    )

    file_desc = FileDescriptorProto(
        name=file_name,
        package=package,
        syntax="proto3",
    )

    for message_desc in collected.values():
        file_desc.message_type.append(message_desc)

    file_desc.service.append(service)

    return file_desc
