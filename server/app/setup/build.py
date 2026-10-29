import inspect
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.setup.application import application as declared_application
from app.setup.catalog import MODULES
from app.setup.effects import effect_service, with_effects
from app.setup.files import file_components
from app.setup.structure import ROOT, check_structure
from app.setup.timing import bind_clock
from shared.access.vault import Vault
from shared.application.spec import ApplicationSpec
from shared.cache.backends import Cache, MemoryCache, RedisCache
from shared.config.settings import Settings, check_production
from shared.db.budget import QueryPolicy
from shared.db.database import Database
from shared.db.ownership import check_migrations
from shared.effects.spec import EffectAdapter, ProviderSpec
from shared.errors.framework import ConfigError
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
from shared.remote_calls.service import RemoteService
from shared.telemetry.service import Telemetry

log = logging.getLogger("server.setup")


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

    async def close(self) -> None:
        await self.runtime.heavy.close(self.settings.job_shutdown_seconds)
        if self.runtime.effects is not None:
            await self.runtime.effects.close()
        await self.recorder.flush()
        if self.models is not None:
            await self.models.close()
        await self.remotes.close()
        await self.cache.close()
        self.telemetry.close()
        if self.legacy is not None:
            await self.legacy.close()
        await self.database.close()


def build(
    settings: Settings,
    *,
    modules: Sequence[Module] | None = None,
    provider: ModelProvider | None = None,
    application: ApplicationSpec | None = None,
    effect_adapters: dict[ProviderSpec, EffectAdapter] | None = None,
) -> Services:
    specification = application or declared_application()
    settings = specification.prepare(settings)
    registered = list(specification.modules) if specification.modules is not None else MODULES
    if modules is None:
        check_structure(registered)
        migration_errors = check_migrations(ROOT, registered, settings)
        if migration_errors:
            raise ConfigError(migration_errors)
    selected = enabled_modules(settings, registered) if modules is None else modules
    catalog = product_catalog(settings, specification, selected)
    problems = check_production(
        settings,
        needs_vault=bool(specification.providers) or "vault" in store_requirements(catalog),
    )
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
    if provider is None and specification.model_provider is not None and settings.env != "test":
        provider = specification.model_provider(settings)
    models = model_service(settings, catalog, provider)
    services = finish_build(settings, catalog, database, recorder, models)
    services.runtime.effects = effect_service(
        settings, specification, database, services.remotes, effect_adapters
    )
    services.runtime.query_policy = query_policy(settings)
    services.runtime.allow_simulation = settings.env == "test"
    bind_clock(services, specification.clock or services.runtime.clock)
    return services


def product_catalog(
    settings: Settings, spec: ApplicationSpec, modules: Sequence[Module]
) -> Catalog:
    selected = with_effects(spec, modules)
    from shared.scenarios.simulation import check_simulations

    catalog = Catalog(selected, strict_endpoints=settings.remote_endpoints_strict)
    check_simulations(catalog, settings.env)
    return catalog


def enabled_modules(settings: Settings, registered: Sequence[Module] | None = None) -> list[Module]:
    registered = MODULES if registered is None else registered
    unknown = set(settings.disabled_modules) - {module.name for module in registered}
    if unknown:
        raise ConfigError([f"APP_DISABLED_MODULES 中的模块没有登记：{', '.join(sorted(unknown))}"])
    return [module for module in registered if module.name not in settings.disabled_modules]


def unconfigured_remotes(settings: Settings, catalog: Catalog) -> list[str]:
    if settings.env != "production":
        return []
    return [
        f"模块 {module.name} 声明的外部系统 {item.name}（{item.title}）没有在 APP_REMOTES 中配置"
        for module in catalog.modules.values()
        for item in module.remotes
        if item.name not in settings.remotes
    ]


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


def vault_service(settings: Settings, needs: set[str]) -> Vault | None:
    return (
        Vault([key.get_secret_value() for key in settings.data_keys]) if "vault" in needs else None
    )


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


def remote_service(settings: Settings, catalog: Catalog) -> RemoteService:
    used = {item.name for module in catalog.modules.values() for item in module.remotes}
    return RemoteService(
        {key: value for key, value in settings.remotes.items() if key in used},
        strict_endpoints=settings.remote_endpoints_strict,
    )


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


def store_requirements(catalog: Catalog) -> set[str]:
    return {
        name
        for module in catalog.modules.values()
        if module.store is not None
        for name in inspect.signature(module.store).parameters
    }


def query_policy(settings: Settings) -> QueryPolicy:
    return QueryPolicy(settings.env, settings.query_budget_mode, settings.query_budget_explain)
