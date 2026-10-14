"""
产品的配置、组装扩展与后台入口只声明一次，离线结构查看不读取环境和凭据。
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic_settings import PydanticBaseSettingsSource

from shared.config.settings import Settings
from shared.effects.spec import EffectAdapter, ProviderSpec
from shared.errors.framework import ConfigError
from shared.model_calls.providers import ModelProvider
from shared.modules.module import Module
from shared.remote_calls.service import RemoteService
from shared.timing.clock import Clock

FRAMEWORK_VERSION = "3.2.0"


# 后台扩展与框架队列共用服务和停止信号，不再单独创建连接池和记录器。
@dataclass(frozen=True)
class WorkerSpec:
    name: str
    run: Callable[[Any, asyncio.Event], Awaitable[None]]
    title: str = ""
    resources: tuple[str, ...] = ()


# 产品的实际API、worker、文档与测试共同采用这一份声明。
@dataclass(frozen=True)
class ApplicationSpec:
    name: str = "单体后端模板"
    version: str = "0.1.0"
    settings_type: type[Settings] = Settings
    modules: tuple[Module, ...] | None = None
    routers: tuple[Any, ...] = ()
    configure: Callable[[Settings], Settings] | None = None
    model_provider: Callable[[Settings], ModelProvider | None] | None = None
    api_setup: Callable[[Any], None] | None = None
    workers: tuple[WorkerSpec, ...] = ()
    providers: tuple[ProviderSpec, ...] = ()
    adapters: Callable[[Settings, RemoteService], dict[ProviderSpec, EffectAdapter]] | None = None
    clock: Clock | None = None

    # 实际运行可以读取部署环境，离线和测试配置只接受显式输入及声明默认值。
    def settings(
        self, mode: Literal["runtime", "offline", "test"] = "runtime", **values: Any
    ) -> Settings:
        self.validate()
        if mode == "runtime":
            settings = self.settings_type(**values)
        else:
            settings_type = cast(
                type[Settings],
                type(
                    f"Isolated{self.settings_type.__name__}",
                    (self.settings_type,),
                    {"settings_customise_sources": classmethod(initial_sources)},
                ),
            )
            settings = settings_type(_env_file=None, **{"env": "test", **values})
        return self.prepare(settings)

    # 显式传入的测试配置同样应用产品策略，每份配置只组装一次。
    def prepare(self, settings: Settings) -> Settings:
        if not isinstance(settings, self.settings_type):
            return self.settings("offline", **settings.model_dump())
        if getattr(settings, "_application_spec", None) is self:
            return settings
        settings.name = self.name
        settings = self.configure(settings) if self.configure else settings
        object.__setattr__(settings, "_application_spec", self)
        return settings

    # 声明错误在创建服务前给出，不在后台任务启动后才发现重复入口。
    def validate(self) -> None:
        problems = []
        if not self.name.strip() or not self.version.strip():
            problems.append("产品必须声明名称和产品版本")
        names = [worker.name for worker in self.workers]
        if len(names) != len(set(names)) or any(
            not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name == "jobs" for name in names
        ):
            problems.append("后台扩展名称必须唯一且不能使用保留名称jobs")
        if not isinstance(self.settings_type, type) or not issubclass(self.settings_type, Settings):
            problems.append("产品配置必须继承框架Settings")
        if len({spec.name for spec in self.providers}) != len(self.providers):
            problems.append("产品外部效果名称不能重复")
        for spec in self.providers:
            spec.validate()
        if problems:
            raise ConfigError(problems)

    # 只输出声明名称与位置，不执行模型、网络或后台扩展。
    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "product_version": self.version,
            "framework_version": FRAMEWORK_VERSION,
            "settings_type": location(self.settings_type),
            "configure": location(self.configure),
            "api_setup": location(self.api_setup),
            "model_provider": location(self.model_provider),
            "providers": [spec.shape() for spec in self.providers],
            "adapters": location(self.adapters),
            "clock": location(self.clock),
            "modules": None if self.modules is None else [item.name for item in self.modules],
            "routers": [getattr(router, "prefix", "") for router in self.routers],
            "workers": [
                {"name": "jobs", "title": "框架任务队列"},
                *[
                    {
                        "name": worker.name,
                        "title": worker.title,
                        "run": location(worker.run),
                        "resources": list(worker.resources),
                    }
                    for worker in self.workers
                ],
            ],
        }


# BaseSettings的环境与文件源均不参加隔离配置，产品校验器仍正常运行。
def initial_sources(
    cls: type[Settings],
    settings_cls: type[Settings],
    init_settings: PydanticBaseSettingsSource,
    env_settings: PydanticBaseSettingsSource,
    dotenv_settings: PydanticBaseSettingsSource,
    file_secret_settings: PydanticBaseSettingsSource,
) -> tuple[PydanticBaseSettingsSource, ...]:
    return (init_settings,)


# 源码位置不包含对象repr，避免闭包或配置对象的秘密进入声明摘要。
def location(value: Any) -> str:
    if value is None:
        return ""
    module = getattr(value, "__module__", type(value).__module__)
    name = getattr(value, "__qualname__", type(value).__qualname__)
    return f"{module}.{name}"
