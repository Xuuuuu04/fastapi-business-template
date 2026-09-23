"""
启动组装：按配置创建数据库、运行记录、大模型服务、任务表和执行器。
接口进程和 worker 进程都用这里组装，保证两边使用同一份模块目录。
创建过程不连接数据库，连接在第一次使用时建立。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.setup.catalog import MODULES
from shared.config.settings import Settings, check_production
from shared.db.database import Database
from shared.errors.framework import ConfigError
from shared.flow.runtime import Runtime
from shared.jobs.queue import JobQueue
from shared.model_calls.providers import FakeModel, ModelProvider, OpenAICompatible
from shared.model_calls.service import ModelService
from shared.modules.catalog import Catalog
from shared.modules.module import Module
from shared.records.recorder import Recorder
from shared.records.stores import MemoryRunStore, RunStore, SqlRunStore

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

    # 按创建的相反顺序释放资源。
    async def close(self) -> None:
        await self.recorder.flush()
        await self.models.close()
        await self.database.close()


# 按配置组装全部服务；modules 和 provider 只在测试中替换。
def build(
    settings: Settings,
    *,
    modules: Sequence[Module] | None = None,
    provider: ModelProvider | None = None,
) -> Services:
    problems = check_production(settings)
    if problems:
        raise ConfigError(problems)
    catalog = Catalog(MODULES if modules is None else modules)
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
    queue = JobQueue(catalog, database)
    runtime = Runtime(
        catalog,
        database,
        recorder,
        models=models,
        jobs=queue,
        code_version=settings.code_version,
        step_checks=settings.extra_step_checks(),
    )
    return Services(settings, catalog, database, recorder, models, queue, runtime)


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
