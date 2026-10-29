from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter


class Telemetry:
    def __init__(
        self, endpoint: str, service_name: str, exporter: SpanExporter | None = None
    ) -> None:
        self.provider: TracerProvider | None = None
        if endpoint or exporter is not None:
            provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
            processor = (
                SimpleSpanProcessor(exporter)
                if exporter is not None
                else BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )
            provider.add_span_processor(processor)
            self.provider = provider
            self.tracer = provider.get_tracer("backend-template")
        else:
            self.tracer = trace.get_tracer("backend-template")

    def close(self) -> None:
        if self.provider is not None:
            self.provider.shutdown()
