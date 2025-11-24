import logging
from logging import Logger

from spakky.application.application_context import ApplicationContext
from spakky.pod.annotations.pod import Pod
from spakky.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.pod.interfaces.aware.container_aware import IContainerAware
from spakky.pod.interfaces.aware.logger_aware import ILoggerAware
from spakky.pod.post_processors.aware_post_processor import (
    ApplicationContextAwareProcessor,
)


def test_application_context_aware_processor_with_container_aware() -> None:
    """Test that ApplicationContextAwareProcessor sets container for IContainerAware pods"""

    @Pod()
    class ServiceWithContainerAware(IContainerAware):
        def __init__(self) -> None:
            self.container: object | None = None

        def set_container(self, container: object) -> None:
            self.container = container

    context = ApplicationContext()
    logger = logging.getLogger("test")
    processor = ApplicationContextAwareProcessor(context, logger)

    service = ServiceWithContainerAware()
    assert service.container is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, ServiceWithContainerAware)
    assert processed_service.container is context


def test_application_context_aware_processor_with_application_context_aware() -> None:
    """Test that ApplicationContextAwareProcessor sets app context for IApplicationContextAware pods"""

    @Pod()
    class ServiceWithAppContextAware(IApplicationContextAware):
        def __init__(self) -> None:
            self.app_context: object | None = None

        def set_application_context(self, application_context: object) -> None:
            self.app_context = application_context

    context = ApplicationContext()
    logger = logging.getLogger("test")
    processor = ApplicationContextAwareProcessor(context, logger)

    service = ServiceWithAppContextAware()
    assert service.app_context is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, ServiceWithAppContextAware)
    assert processed_service.app_context is context


def test_application_context_aware_processor_with_logger_aware() -> None:
    """Test that ApplicationContextAwareProcessor sets logger for ILoggerAware pods"""

    @Pod()
    class ServiceWithLoggerAware(ILoggerAware):
        def __init__(self) -> None:
            self.logger: Logger | None = None

        def set_logger(self, logger: Logger) -> None:
            self.logger = logger

    context = ApplicationContext()
    logger = logging.getLogger("test")
    processor = ApplicationContextAwareProcessor(context, logger)

    service = ServiceWithLoggerAware()
    assert service.logger is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, ServiceWithLoggerAware)
    assert processed_service.logger is logger


def test_application_context_aware_processor_with_non_aware_pod() -> None:
    """Test that ApplicationContextAwareProcessor returns pod unchanged if it's not aware"""

    @Pod()
    class RegularService:
        def __init__(self) -> None:
            self.value = "test"

    context = ApplicationContext()
    logger = logging.getLogger("test")
    processor = ApplicationContextAwareProcessor(context, logger)

    service = RegularService()
    processed_service = processor.post_process(service)

    assert isinstance(processed_service, RegularService)
    assert processed_service is service
    assert processed_service.value == "test"
