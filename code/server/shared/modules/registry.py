"""
校验模块目录并限制跨模块调用。
只支持显式注册的同步操作，不负责发现或热加载未知插件。
"""

import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import partial
from types import MappingProxyType
from typing import Any

from shared.monitor.trace import Monitor

current: ContextVar[str] = ContextVar("current_module", default="")


@dataclass(frozen=True)
class Module:
    name: str
    version: str
    source: str
    actions: tuple[str, ...]
    calls: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    entry: bool = False


class Registry:
    # 验证模块和依赖后冻结注册表。
    def __init__(self, modules: tuple[Module, ...], monitor: Monitor) -> None:
        self.monitor = monitor
        self.modules = MappingProxyType({module.name: module for module in modules})
        if len(self.modules) != len(modules):
            raise ValueError("模块名称重复")
        self.validate()

    # 检查未知依赖、重复操作和循环依赖。
    def validate(self) -> None:
        for module in self.modules.values():
            if len(module.actions) != len(set(module.actions)):
                raise ValueError(f"公开操作重复：{module.name}")
            if not set(module.scopes) <= set(module.actions):
                raise ValueError(f"事务操作未公开：{module.name}")
            if any(name not in self.modules for name in module.calls):
                raise ValueError(f"依赖模块未注册：{module.name}")

        # 沿依赖树查找循环。
        def visit(name: str, chain: tuple[str, ...]) -> None:
            if name in chain:
                raise ValueError("模块依赖存在循环")
            for target in self.modules[name].calls:
                visit(target, (*chain, name))

        for name in self.modules:
            visit(name, ())

    # 建立受约束的调用入口并核对实现的方法。
    def bind(self, caller: str, target: str, instance: object) -> "Port":
        if caller not in self.modules or target not in self.modules:
            raise ValueError("调用方或目标未注册")
        if target not in self.modules[caller].calls:
            raise ValueError(f"调用关系未注册：{caller} -> {target}")
        for action in self.modules[target].actions:
            method = getattr(instance, action, None)
            if not callable(method) or inspect.iscoroutinefunction(method):
                raise ValueError(f"缺少同步公开操作：{target}.{action}")
            if inspect.isgeneratorfunction(method):
                raise ValueError("生成器需独立设计，不允许直接注册")
        return Port(self, caller, target, instance)

    # 根据当前执行模块验证调用身份。
    def authorize(self, caller: str, target: str, action: str) -> Module:
        if caller not in self.modules or target not in self.modules:
            raise PermissionError("调用方或目标未注册")
        if target not in self.modules[caller].calls:
            raise PermissionError("调用关系未注册")
        active = current.get()
        if active != caller and (active or not self.modules[caller].entry):
            raise PermissionError("当前模块无权使用此调用入口")
        module = self.modules[target]
        if action not in module.actions:
            raise AttributeError(f"操作未注册：{target}.{action}")
        return module

    # 执行一次普通模块调用并记录安全摘要。
    def call(
        self, caller: str, target: str, instance: object, action: str, *args, **kwargs
    ) -> Any:
        module = self.authorize(caller, target, action)
        if action in module.scopes:
            return self.scope(caller, target, instance, action, *args, **kwargs)
        inputs = [type(value).__name__ for value in (*args, *kwargs.values())]
        with self.monitor.span(caller, target, action, module.version, inputs) as span:
            token = current.set(target)
            try:
                result = getattr(instance, action)(*args, **kwargs)
                if span is not None:
                    span.output = type(result).__name__
                return result
            finally:
                current.reset(token)

    # 在事务整个持续期间记录状态而不改变业务调用身份。
    @contextmanager
    def scope(
        self, caller: str, target: str, instance: object, action: str, *args, **kwargs
    ) -> Iterator[Any]:
        module = self.authorize(caller, target, action)
        with self.monitor.span(caller, target, action, module.version, []) as span:
            with getattr(instance, action)(*args, **kwargs) as result:
                if span is not None:
                    span.output = "context"
                yield result

    # 导出模块目录和静态依赖图。
    def describe(self) -> dict:
        return {"modules": [asdict(module) for module in self.modules.values()]}


class Port:
    # 保存本次组装的调用关系和具体实现。
    def __init__(self, registry: Registry, caller: str, target: str, instance: object) -> None:
        self._registry = registry
        self._caller = caller
        self._target = target
        self._instance = instance

    # 仅暴露目标模块登记过的方法。
    def __getattr__(self, action: str) -> Any:
        if action not in self._registry.modules[self._target].actions:
            raise AttributeError(f"操作未注册：{self._target}.{action}")
        return partial(self._registry.call, self._caller, self._target, self._instance, action)
