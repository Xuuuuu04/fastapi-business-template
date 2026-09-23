"""
启动组装：按配置创建数据库、运行记录、大模型服务、任务表和执行器。
接口进程和 worker 进程都用这里组装，保证两边使用同一份模块目录。
创建过程不连接数据库，连接在第一次使用时建立。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.setup.catalog import MODULES
from shared.cache.backends import Cache, MemoryCache, RedisCache
from shared.config.settings import Settings, check_production
from shared.db.database import Database
from shared.errors.framework import ConfigError
from shared.files.storage import FileStorage, LocalFiles, S3Files, S3Options
from shared.files.uploads import UploadArea
from shared.flow.runtime import Runtime
from shared.jobs.queue import JobQueue
from shared.model_calls.providers import FakeModel, ModelProvider, OpenAICompatible
from shared.model_calls.service import ModelService
from shared.modules.catalog import Catalog
from shared.modules.module import Module
from shared.records.recorder import Recorder
from shared.records.stores import MemoryRunStore, RunStore, SqlRunStore
from shared.remote_calls.service import RemoteService
from shared.telemetry.service import Telemetry

log = logging.getLogger("server.setup")


@dataclass
class Services:
    settings: Settings
    catalog: Catalog
    database: Database
    recorder: Recorder
    models: ModelService
    queue: JobQueue
    runtime: Runtime
    remotes: RemoteService
    cache: Cache
    legacy: Database | None
    uploads: UploadArea
    telemetry: Telemetry

    # 按创建的相反顺序释放资源。
    async def close(self) -> None:
        await self.recorder.flush()
        await self.models.close()
        await self.remotes.close()
        await self.cache.close()
        self.telemetry.close()
        if self.legacy is not None:
            await self.legacy.close()
        await self.database.close()


# 按配置组装全部服务；modules 和 provider 只在测试中替换。
def build(
    settings: Settings,
    *,
    modules: Sequence[Module] | None = None,
    provider: ModelProvider | None = None,
) -> Services:
    catalog = Catalog(MODULES if modules is None else modules)
    problems = check_production(settings) + unconfigured_remotes(settings, catalog)
    if problems:
        raise ConfigError(problems)
    database = Database(
        settings.database_url,
        pool_size=settings.database_pool_size,
        wait_seconds=settings.database_wait_seconds,
    )
    store: RunStore = (
        MemoryRunStore(settings.run_record_limit)
        if settings.run_records == "memory"
        else SqlRunStore(database)
    )
    recorder = Recorder(store, buffer=settings.run_record_buffer)
    models = model_service(settings, catalog, provider)
    return finish_build(settings, catalog, database, recorder, models)


# 生产环境中，模块声明的每个外部系统都必须配置地址。
def unconfigured_remotes(settings: Settings, catalog: Catalog) -> list[str]:
    if settings.env != "production":
        return []
    return [
        f"模块 {module.name} 声明的外部系统 {item.name}（{item.title}）没有在 APP_REMOTES 中配置"
        for module in catalog.modules.values()
        for item in module.remotes
        if item.name not in settings.remotes
    ]


# 创建外部服务、文件服务、任务入口和执行器。
def finish_build(
    settings: Settings,
    catalog: Catalog,
    database: Database,
    recorder: Recorder,
    models: ModelService,
) -> Services:
    remotes = RemoteService(settings.remotes)
    cache: Cache = RedisCache(settings.cache_url) if settings.cache_url else MemoryCache()
    legacy = Database(settings.legacy_database_url) if settings.legacy_database_url else None
    storage, uploads = file_components(settings)
    telemetry = Telemetry(settings.otel_endpoint, settings.name)
    queue = JobQueue(catalog, database)
    runtime = Runtime(
        catalog,
        database,
        recorder,
        models=models,
        jobs=queue,
        remotes=remotes,
        cache=cache,
        files=storage,
        uploads=uploads,
        legacy=legacy,
        telemetry=telemetry,
        code_version=settings.code_version,
        step_checks=settings.extra_step_checks(),
    )
    return Services(
        settings,
        catalog,
        database,
        recorder,
        models,
        queue,
        runtime,
        remotes,
        cache,
        legacy,
        uploads,
        telemetry,
    )


# 创建文件存储与上传临时区。
def file_components(settings: Settings) -> tuple[FileStorage, UploadArea]:
    uploads = UploadArea(
        Path(settings.upload_root), settings.upload_max_bytes, settings.upload_suffixes
    )
    return file_service(settings), uploads


# 根据配置选择本地文件目录或 S3 兼容存储。
def file_service(settings: Settings) -> FileStorage:
    if settings.file_storage == "local":
        return LocalFiles(Path(settings.file_root))
    if not settings.s3_bucket:
        raise ConfigError(["APP_FILE_STORAGE=s3 时必须配置 APP_S3_BUCKET"])
    options = S3Options(
        settings.s3_bucket,
        settings.s3_endpoint,
        settings.s3_region,
        settings.s3_access_key,
        settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else "",
    )
    return S3Files(options)


# 选择大模型服务：配置了就用真实服务；本地和测试没配置时用模拟回复，生产环境没配置则拒绝启动。
def model_service(
    settings: Settings, catalog: Catalog, provider: ModelProvider | None
) -> ModelService:
    prompts = catalog.prompts()
    if provider is None and settings.has_model():
        key = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
        provider = OpenAICompatible(
            settings.model_base_url, key, settings.model_name, settings.model_timeout
        )
    if provider is None:
        if settings.env == "production" and prompts:
            problem = "模块声明了提示词，但生产环境没有配置 APP_MODEL_BASE_URL 等大模型设置"
            raise ConfigError([problem])
        if prompts:
            log.warning("model_not_configured using=fake prompts=%s", len(prompts))
        provider = FakeModel()
    service = ModelService(
        provider, concurrency=settings.model_concurrency, keep_text=settings.model_keep_text
    )
    service.load(prompts)
    return service
