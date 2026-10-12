# OpenTelemetry

把 `APP_OTEL_ENDPOINT` 配置为 OTLP HTTP traces 的接收地址后，运行和步骤会导出跨度；属性只包含操作名、步骤名、运行编号、状态和耗时，不含业务正文、密钥或字段原值。没有配置时使用空实现。接口进程和 worker 都由 `app/setup/build.py` 建立导出器，关闭时刷新并释放。
