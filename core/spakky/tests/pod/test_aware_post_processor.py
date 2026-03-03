from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.aware.tag_registry_aware import ITagRegistryAware
from spakky.core.pod.interfaces.tag_registry import ITagRegistry
from spakky.core.pod.post_processors.aware_post_processor import (
    ApplicationContextAwareProcessor,
)


def test_application_context_aware_processor_with_container_aware() -> None:
    """ApplicationContextAwareProcessor가 IContainerAware Pod에 container를 설정함을 검증한다."""

    @Pod()
    class ServiceWithContainerAware(IContainerAware):
        def __init__(self) -> None:
            self.container: object | None = None

        def set_container(self, container: object) -> None:
            self.container = container

    context = ApplicationContext()
    processor = ApplicationContextAwareProcessor(context)

    service = ServiceWithContainerAware()
    assert service.container is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, ServiceWithContainerAware)
    assert processed_service.container is context


def test_application_context_aware_processor_with_application_context_aware() -> None:
    """ApplicationContextAwareProcessor가 IApplicationContextAware Pod에 application context를 설정함을 검증한다."""

    @Pod()
    class ServiceWithAppContextAware(IApplicationContextAware):
        def __init__(self) -> None:
            self.app_context: object | None = None

        def set_application_context(self, application_context: object) -> None:
            self.app_context = application_context

    context = ApplicationContext()
    processor = ApplicationContextAwareProcessor(context)

    service = ServiceWithAppContextAware()
    assert service.app_context is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, ServiceWithAppContextAware)
    assert processed_service.app_context is context


def test_application_context_aware_processor_with_non_aware_pod() -> None:
    """ApplicationContextAwareProcessor가 Aware 인터페이스를 구현하지 않은 Pod을 변경 없이 반환함을 검증한다."""

    @Pod()
    class RegularService:
        def __init__(self) -> None:
            self.value = "test"

    context = ApplicationContext()
    processor = ApplicationContextAwareProcessor(context)

    service = RegularService()
    processed_service = processor.post_process(service)

    assert isinstance(processed_service, RegularService)
    assert processed_service is service
    assert processed_service.value == "test"


def test_application_context_aware_processor_with_tag_registry_aware() -> None:
    """ApplicationContextAwareProcessor가 ITagRegistryAware Pod에 tag registry를 설정함을 검증한다."""

    @Pod()
    class ServiceWithTagRegistryAware(ITagRegistryAware):
        def __init__(self) -> None:
            self.tag_registry: ITagRegistry | None = None

        def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
            self.tag_registry = tag_registry

    context = ApplicationContext()
    processor = ApplicationContextAwareProcessor(context)

    service = ServiceWithTagRegistryAware()
    assert service.tag_registry is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, ServiceWithTagRegistryAware)
    assert processed_service.tag_registry is context


def test_application_context_aware_processor_with_multiple_aware_interfaces() -> None:
    """ApplicationContextAwareProcessor가 여러 Aware 인터페이스를 구현한 Pod을 올바르게 처리함을 검증한다."""

    @Pod()
    class MultiAwareService(
        IContainerAware, ITagRegistryAware, IApplicationContextAware
    ):
        def __init__(self) -> None:
            self.container: object | None = None
            self.tag_registry: ITagRegistry | None = None
            self.app_context: object | None = None

        def set_container(self, container: object) -> None:
            self.container = container

        def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
            self.tag_registry = tag_registry

        def set_application_context(self, application_context: object) -> None:
            self.app_context = application_context

    context = ApplicationContext()
    processor = ApplicationContextAwareProcessor(context)

    service = MultiAwareService()
    assert service.container is None
    assert service.tag_registry is None
    assert service.app_context is None

    processed_service = processor.post_process(service)
    assert isinstance(processed_service, MultiAwareService)
    assert processed_service.container is context
    assert processed_service.tag_registry is context
    assert processed_service.app_context is context
