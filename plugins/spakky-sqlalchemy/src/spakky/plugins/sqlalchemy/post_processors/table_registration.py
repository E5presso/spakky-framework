"""Post-processor for automatic table registration."""

from logging import getLogger

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.plugins.sqlalchemy.orm.error import InvalidTableScopeError
from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from spakky.plugins.sqlalchemy.orm.table import Table

logger = getLogger(__name__)


@Order(100)  # Run after other post-processors
@Pod()
class TableRegistrationPostProcessor(IPostProcessor, IContainerAware):
    """Post-processor that registers @Table annotated classes with ModelRegistry.

    Discovers all Pods with @Table annotation during application startup
    and registers them with the SQLAlchemy ModelRegistry for ORM mapping.

    Since @Table classes use DEFINITION scope, they are registered in the
    IoC container but never instantiated as managed beans. This post-processor
    uses the container's pod registry to discover them.
    """

    __container: IContainer
    __processed: bool = False

    def set_container(self, container: IContainer) -> None:
        """Set the container for accessing pod registry.

        Args:
            container: The IoC container.
        """
        self.__container = container

    def post_process(self, pod: object) -> object:
        """Process pods and register tables when ModelRegistry is available.

        This method is called for each pod during initialization.
        When the ModelRegistry is processed, we trigger table registration
        for all discovered @Table annotated classes.

        Args:
            pod: The Pod being processed.

        Returns:
            The unmodified Pod.
        """
        # Only process once when ModelRegistry itself is being post-processed
        if not isinstance(pod, ModelRegistry):
            return pod

        if self.__processed:
            return pod

        self._register_all_tables(pod)
        self.__processed = True

        return pod

    def _register_all_tables(self, registry: ModelRegistry) -> None:
        """Register all @Table annotated classes with the registry.

        Iterates through all registered pods in the container and
        registers those with DEFINITION scope and @Table annotation.

        Args:
            registry: The ModelRegistry to register tables with.
        """
        # Iterate through all registered pods
        for pod_meta in self.__container.pods.values():
            # Check if this pod has Table annotation
            if not Table.exists(pod_meta.target):
                continue

            # Validate DEFINITION scope requirement
            if pod_meta.scope != Pod.Scope.DEFINITION:
                raise InvalidTableScopeError

            # Register the entity class with ModelRegistry
            entity_cls = pod_meta.type_
            try:
                registry.register(entity_cls)
                logger.debug(
                    f"[{type(self).__name__}] Registered table {entity_cls.__name__!r}"
                )
            except Exception as e:  # pragma: no cover
                logger.error(
                    f"[{type(self).__name__}] Failed to register table "
                    f"{entity_cls.__name__!r}: {e}"
                )
                raise
