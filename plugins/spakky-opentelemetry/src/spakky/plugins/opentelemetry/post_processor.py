"""Post-processor that configures OpenTelemetry SDK and replaces W3CTracePropagator."""

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.tracing.w3c_propagator import W3CTracePropagator
from typing_extensions import override

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from spakky.plugins.opentelemetry.config import ExporterType, OpenTelemetryConfig
from spakky.plugins.opentelemetry.error import UnsupportedExporterTypeError
from spakky.plugins.opentelemetry.propagator import OTelTracePropagator


@Order(0)
@Pod()
class OTelSetupPostProcessor(IPostProcessor, IContainerAware):
    """Initializes OTel TracerProvider and replaces W3CTracePropagator.

    On first ``post_process`` call, configures the global TracerProvider
    with the user's chosen exporter. For every pod that is an instance of
    W3CTracePropagator, returns an OTelTracePropagator instead.
    """

    __container: IContainer
    __configured: bool

    def __init__(self) -> None:
        super().__init__()
        self.__configured = False

    @override
    def set_container(self, container: IContainer) -> None:
        self.__container = container

    @override
    def post_process(self, pod: object) -> object:
        """Configure TracerProvider on first call; replace W3CTracePropagator.

        Args:
            pod: The Pod instance being processed.

        Returns:
            OTelTracePropagator if pod is W3CTracePropagator, else pod unchanged.
        """
        if not self.__configured:
            self.__configured = True
            self._configure_tracer_provider()
        if isinstance(pod, W3CTracePropagator):
            return OTelTracePropagator()
        return pod

    def _configure_tracer_provider(self) -> None:
        """Set up OTel TracerProvider from OpenTelemetryConfig."""
        config = self.__container.get(OpenTelemetryConfig)
        resource = Resource.create({"service.name": config.service_name})
        sampler = TraceIdRatioBased(config.sample_rate)
        provider = TracerProvider(resource=resource, sampler=sampler)

        exporter = self._create_exporter(config)
        if exporter is not None:
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)

    @staticmethod
    def _create_exporter(config: OpenTelemetryConfig) -> SpanExporter | None:
        """Create a SpanExporter based on config.exporter_type.

        Args:
            config: The OpenTelemetry configuration.

        Returns:
            A SpanExporter instance, or None for ExporterType.NONE.

        Raises:
            UnsupportedExporterTypeError: If the exporter type is unknown.
        """
        match config.exporter_type:
            case ExporterType.CONSOLE:
                return ConsoleSpanExporter()
            case ExporterType.OTLP:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # pyrefly: ignore - lazy import for optional dependency
                    OTLPSpanExporter,
                )

                return OTLPSpanExporter(endpoint=config.exporter_endpoint)
            case ExporterType.NONE:
                return None
            case _:  # pragma: no cover - exhaustive StrEnum
                raise UnsupportedExporterTypeError()
