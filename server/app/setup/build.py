"""
启动组装：按配置创建数据库、运行记录、大模型服务、任务表和执行器。
接口进程和 worker 进程都用这里组装，保证两边使用同一份模块目录。
创建过程不连接数据库，连接在第一次使用时建立。
"""

import inspect
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.setup.catalog import MODULES
from app.setup.operations import with_operations
from app.setup.structure import ROOT, check_structure
from shared.access.vault import Vault
from shared.cache.backends import Cache, MemoryCache, RedisCache
from shared.config.settings import Settings, check_production
from shared.db.database import Database
from shared.db.ownership import check_migrations
from shared.errors.framework import ConfigError
from shared.files.storage import FileStorage, LocalFiles, S3Files, S3Options
from shared.files.uploads import UploadArea
from shared.flow.heavy import HeavySteps
from shared.flow.runtime import Runtime
from shared.jobs.queue import JobQueue
from shared.model_calls.providers import FakeModel, ModelProvider, OpenAICompatible
from shared.model_calls.service import ModelService
from shared.modules.catalog import Catalog
from shared.modules.module import Module
from shared.records.recorder import Recorder
from shared.records.stores import MemoryRunStore, RunStore, SqlRunStore
from shared.records.version import source_version
from shared.remote_calls.service import RemoteService
from shared.telemetry.service import Telemetry

log = logging.getLogger("server.setup")


# 接口与后台进程使用的服务对象，集中管理创建结果和退出时的资源释放。
@dataclass
class Services:
    settings: Settings
    catalog: Catalog
    database: Database
    recorder: Recorder
    models: ModelService | None
    queue: JobQueue
    runtime: Runtime
    remotes: RemoteService
    cache: Cache
    legacy: Database | None
    uploads: UploadArea | None
    telemetry: Telemetry

    # 按创建的相反顺序释放资源。
    async def close(self) -> None:
        await self.runtime.heavy.close(self.settings.job_shutdown_seconds)
        await self.recorder.flush()
        if self.models is not None:
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
    if modules is None:
        check_structure(MODULES)
        migration_errors = check_migrations(ROOT, MODULES, settings)
        if migration_errors:
            raise ConfigError(migration_errors)
    selected = enabled_modules(settings) if modules is None else modules
    catalog = Catalog(
        with_operations(settings, selected), strict_endpoints=settings.remote_endpoints_strict
    )
    problems = check_production(settings, needs_vault="vault" in store_requirements(catalog))
    problems += unconfigured_remotes(settings, catalog)
    if problems:
        raise ConfigError(problems)
    database = Database(
        settings.database_url,
        pool_size=settings.database_pool_size,
        wait_seconds=settings.database_wait_seconds,
        org_setting=settings.database_org_setting,
    )
    store: RunStore = (
        MemoryRunStore(settings.run_record_limit)
        if settings.run_records == "memory"
        else SqlRunStore(database)
    )
    recorder = Recorder(store, buffer=settings.run_record_buffer)
    models = model_service(settings, catalog, provider)
    services = finish_build(settings, catalog, database, recorder, models)
    if modules is None:
        services.runtime.source_version = source_version(ROOT)
    return services


# 关闭模块只影响接口和执行入口，保留其数据库表与历史数据。
def enabled_modules(settings: Settings) -> list[Module]:
    unknown = set(settings.disabled_modules) - {module.name for module in MODULES}
    if unknown:
        raise ConfigError([f"APP_DISABLED_MODULES 中的模块没有登记：{', '.join(sorted(unknown))}"])
    return [module for module in MODULES if module.name not in settings.disabled_modules]


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
    models: ModelService | None,
) -> Services:
    remotes = remote_service(settings, catalog)
    cache = cache_service(settings)
    needs = store_requirements(catalog)
    legacy = (
        Database(settings.legacy_database_url)
        if "legacy" in needs and settings.legacy_database_url
        else None
    )
    storage, uploads = file_components(settings) if "files" in needs else (None, None)
    telemetry = Telemetry(settings.otel_endpoint, settings.name)
    queue = JobQueue(catalog, database)
    queue.capacity_enabled = settings.operations.capacity and settings.operations.pause_noncritical
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
        vault=vault_service(settings, needs),
        code_version=settings.code_version,
        step_checks=settings.extra_step_checks(),
        heavy=HeavySteps(settings.heavy_concurrency),
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


# 只为实际使用字段加密的模块创建密钥服务。
def vault_service(settings: Settings, needs: set[str]) -> Vault | None:
    return (
        Vault([key.get_secret_value() for key in settings.data_keys]) if "vault" in needs else None
    )


# 按配置创建有明确连接和操作预算的缓存服务。
def cache_service(settings: Settings) -> Cache:
    return (
        RedisCache(
            settings.cache_url,
            timeout=settings.cache_timeout_seconds,
            max_connections=settings.cache_max_connections,
        )
        if settings.cache_url
        else MemoryCache()
    )


# 创建文件存储与上传临时区。
def file_components(settings: Settings) -> tuple[FileStorage, UploadArea]:
    uploads = UploadArea(
        Path(settings.upload_root), settings.upload_max_bytes, settings.upload_suffixes
    )
    return file_service(settings), uploads


# 只保留启用模块声明过的外部系统地址。
def remote_service(settings: Settings, catalog: Catalog) -> RemoteService:
    used = {item.name for module in catalog.modules.values() for item in module.remotes}
    return RemoteService(
        {key: value for key, value in settings.remotes.items() if key in used},
        strict_endpoints=settings.remote_endpoints_strict,
    )


# 按 APP_FILE_STORAGE 选择文件存储实现。
def file_service(settings: Settings) -> FileStorage:
    if settings.file_storage == "local":
        return LocalFiles(Path(settings.file_root))
    if not settings.s3_bucket:
        raise ConfigError(["APP_FILE_STORAGE=s3 时必须配置 APP_S3_BUCKET"])
    secret = settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else ""
    return S3Files(
        S3Options(
            settings.s3_bucket,
            settings.s3_endpoint,
            settings.s3_region,
            settings.s3_access_key,
            secret,
        )
    )


# 有模块使用大模型时才创建服务；开发时可用模拟回复，生产时必须配置真实服务。
def model_service(
    settings: Settings, catalog: Catalog, provider: ModelProvider | None
) -> ModelService | None:
    prompts = catalog.prompts()
    if not prompts:
        return None
    if provider is None and settings.has_model():
        key = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
        provider = OpenAICompatible(
            settings.model_base_url,
            key,
            settings.model_name,
            settings.model_timeout,
            max_response_bytes=settings.model_max_response_bytes,
        )
    if provider is None:
        if settings.env == "production":
            problem = "模块声明了提示词，但生产环境没有配置 APP_MODEL_BASE_URL 等大模型设置"
            raise ConfigError([problem])
        log.warning("model_not_configured using=fake prompts=%s", len(prompts))
        provider = FakeModel()
    service = ModelService(
        provider, concurrency=settings.model_concurrency, keep_text=settings.model_keep_text
    )
    service.load(prompts)
    return service


# 从已有存储声明读取实际需要的服务，不再要求业务重复维护一份开关。
def store_requirements(catalog: Catalog) -> set[str]:
    return {
        name
        for module in catalog.modules.values()
        if module.store is not None
        for name in inspect.signature(module.store).parameters
    }
