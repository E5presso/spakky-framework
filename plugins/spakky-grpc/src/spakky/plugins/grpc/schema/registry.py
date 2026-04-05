"""Descriptor pool registry for compiled protobuf descriptors.

Manages FileDescriptorProto registration in a descriptor_pool, provides
caching, and returns compiled message classes and service descriptors.
"""

from google.protobuf.descriptor import (
    Descriptor,
    FileDescriptor,
    ServiceDescriptor,
)
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass
from google.protobuf.message import Message

from spakky.plugins.grpc.error import DescriptorAlreadyRegisteredError


class DescriptorRegistry:
    """Registry for protobuf descriptors backed by a DescriptorPool.

    Registers FileDescriptorProto instances, prevents duplicates, and
    provides access to compiled message classes and service descriptors.

    Attributes:
        pool: The underlying DescriptorPool.
    """

    def __init__(self, pool: DescriptorPool | None = None) -> None:
        self.pool: DescriptorPool = pool or DescriptorPool()
        self._registered_files: set[str] = set()

    def register(self, file_proto: FileDescriptorProto) -> FileDescriptor:
        """Register a FileDescriptorProto in the pool.

        Args:
            file_proto: The file descriptor proto to register.

        Returns:
            The compiled FileDescriptor.

        Raises:
            DescriptorAlreadyRegisteredError: If the file is already
                registered.
        """
        if file_proto.name in self._registered_files:
            raise DescriptorAlreadyRegisteredError(file_proto.name)

        self._registered_files.add(file_proto.name)
        serialized = file_proto.SerializeToString()
        self.pool.AddSerializedFile(serialized)
        return self.pool.FindFileByName(file_proto.name)

    def is_registered(self, file_name: str) -> bool:
        """Check if a file is already registered.

        Args:
            file_name: The proto file name.

        Returns:
            True if the file has been registered.
        """
        return file_name in self._registered_files

    def find_message_descriptor(self, full_name: str) -> Descriptor:
        """Find a message descriptor by its fully-qualified name.

        Args:
            full_name: The fully-qualified protobuf message name
                (e.g. ``package.MessageName``).

        Returns:
            The message Descriptor.
        """
        return self.pool.FindMessageTypeByName(full_name)

    def get_message_class(self, full_name: str) -> type[Message]:
        """Get a runtime message class for the given type name.

        Args:
            full_name: The fully-qualified protobuf message name.

        Returns:
            A Message subclass that can be instantiated.
        """
        descriptor = self.find_message_descriptor(full_name)
        return GetMessageClass(descriptor)

    def find_service_descriptor(self, full_name: str) -> ServiceDescriptor:
        """Find a service descriptor by its fully-qualified name.

        Args:
            full_name: The fully-qualified protobuf service name
                (e.g. ``package.ServiceName``).

        Returns:
            The ServiceDescriptor.
        """
        return self.pool.FindServiceByName(full_name)
