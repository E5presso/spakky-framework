"""Descriptor pool registry for compiled protobuf descriptors.

Manages registration of :class:`~google.protobuf.descriptor_pb2.FileDescriptorProto`
into a :class:`~google.protobuf.descriptor_pool.DescriptorPool`, providing
cached access to compiled message classes and service descriptors.
"""

from google.protobuf.descriptor import FileDescriptor, ServiceDescriptor
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass

from spakky.plugins.grpc.error import DescriptorAlreadyRegisteredError


class DescriptorRegistry:
    """Registry for compiled protobuf descriptors.

    Wraps a ``DescriptorPool`` with caching and duplicate registration
    prevention.

    Attributes:
        _pool: The underlying descriptor pool.
        _registered_files: Set of already-registered file names.
        _message_cache: Cache of compiled message classes.
    """

    def __init__(self) -> None:
        self._pool: DescriptorPool = DescriptorPool()
        self._registered_files: set[str] = set()
        self._message_cache: dict[str, type[Message]] = {}

    def register(self, file_descriptor_proto: FileDescriptorProto) -> FileDescriptor:
        """Register a ``FileDescriptorProto`` in the pool.

        Args:
            file_descriptor_proto: The file descriptor to register.

        Returns:
            The compiled FileDescriptor.

        Raises:
            DescriptorAlreadyRegisteredError: If a file with the same name
                is already registered.
        """
        file_name = file_descriptor_proto.name
        if file_name in self._registered_files:
            raise DescriptorAlreadyRegisteredError(file_name)

        self._pool.Add(file_descriptor_proto)
        self._registered_files.add(file_name)
        return self._pool.FindFileByName(file_name)

    def is_registered(self, file_name: str) -> bool:
        """Check whether a file is already registered.

        Args:
            file_name: The proto file name.

        Returns:
            True if registered, False otherwise.
        """
        return file_name in self._registered_files

    def get_message_class(self, package: str, message_name: str) -> type[Message]:
        """Get or create a compiled message class.

        Args:
            package: The protobuf package name.
            message_name: The message type name.

        Returns:
            A protobuf Message subclass for the given type.
        """
        full_name = f"{package}.{message_name}"
        if full_name not in self._message_cache:
            descriptor = self._pool.FindMessageTypeByName(full_name)
            self._message_cache[full_name] = GetMessageClass(descriptor)
        return self._message_cache[full_name]

    def get_service_descriptor(
        self, package: str, service_name: str
    ) -> ServiceDescriptor:
        """Get a compiled service descriptor.

        Args:
            package: The protobuf package name.
            service_name: The service name.

        Returns:
            The compiled ServiceDescriptor.
        """
        full_name = f"{package}.{service_name}"
        return self._pool.FindServiceByName(full_name)

    @property
    def pool(self) -> DescriptorPool:
        """Access the underlying descriptor pool.

        Returns:
            The DescriptorPool instance.
        """
        return self._pool
