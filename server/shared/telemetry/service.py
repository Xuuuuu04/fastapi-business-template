"""
按配置导出运行和步骤跨度；只记录名称、编号、状态，不包含业务数据。
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter


# 将执行过程导出到 OpenTelemetry 服务，未配置时不创建导出对象。
class Telemetry:
    # 配置 OTLP HTTP 导出；空地址时使用 OpenTelemetry 的空实现。
    # exporter 只在测试中传入，跨度结束后立即交给它，便于检查。
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

    # 进程关闭时等待已生成的跨度导出。
    def close(self) -> None:
        if self.provider is not None:
            self.provider.shutdown()
