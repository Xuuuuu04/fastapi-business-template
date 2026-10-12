"""
产品声明、持久分发模块和配置适配器共同组装，离线测试不执行真实适配器工厂。
"""

from collections.abc import Sequence

from shared.access.vault import Vault
from shared.application.spec import ApplicationSpec
from shared.config.settings import Settings
from shared.db.database import Database
from shared.effects.module import make_effect_module
from shared.effects.service import EffectService
from shared.effects.spec import EffectAdapter, ProviderSpec
from shared.effects.storage import EffectStore
from shared.errors.framework import ConfigError
from shared.modules.module import Module
from shared.remote_calls.service import RemoteService


# 模块不能访问产品未登记的供应商，关闭业务不删除已经存在的意图或表。
def with_effects(spec: ApplicationSpec, modules: Sequence[Module]) -> list[Module]:
    unknown = [
        provider.name
        for module in modules
        for provider in module.providers
        if provider not in spec.providers
    ]
    if unknown:
        raise ConfigError([f"模块外部效果未在ApplicationSpec登记：{unknown}"])
    return [*modules, *([make_effect_module(spec.providers)] if spec.providers else [])]


# 真实客户端仅运行环境由工厂创建，测试必须显式注入合成适配器。
def effect_service(
    settings: Settings,
    spec: ApplicationSpec,
    database: Database,
    remotes: RemoteService,
    bindings: dict[ProviderSpec, EffectAdapter] | None,
) -> EffectService | None:
    if not spec.providers:
        return None
    if bindings is None:
        if settings.env == "test":
            return None
        if spec.adapters is None:
            raise ConfigError(["产品声明了ProviderSpec但没有配置适配器工厂"])
        bindings = spec.adapters(settings, remotes)
    if set(bindings) != set(spec.providers):
        raise ConfigError(["供应商适配器与产品ProviderSpec声明不一致"])
    if settings.env == "production" and any(adapter.simulated for adapter in bindings.values()):
        raise ConfigError(["生产组装不能使用模拟外部适配器"])
    vault = Vault([key.get_secret_value() for key in settings.data_keys])
    return EffectService(EffectStore(database, vault), bindings)
