"""
定义步骤 @step 和条件 @condition 的写法。
步骤声明读取和写入哪些字段、调用哪些操作、使用哪些提示词、登记哪些任务；
执行器只按声明提供数据和工具，声明以外的访问会报错。参数名决定步骤能拿到什么：
data 流程数据、store 本模块存储、call 调用其他操作、model 大模型、remote 外部接口、
cache 缓存、emit 流式输出、later 登记任务、publish 发布事件、caller 调用者身份、note 记录数据说明。
"""

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from shared.events.event import Event
from shared.model_calls.prompt import Prompt
from shared.modules.contract import Contract
from shared.remote_calls.remote import Remote

PARAMS = (
    "data",
    "store",
    "call",
    "model",
    "remote",
    "cache",
    "later",
    "publish",
    "caller",
    "note",
    "emit",
)


@dataclass(frozen=True, eq=False)
class Condition:
    func: Callable[[Any], bool]
    name: str
    title: str
    reads: tuple[str, ...]
    source: str


@dataclass(frozen=True, eq=False)
class Step:
    func: Callable[..., Any]
    name: str
    title: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    uses: tuple[Contract[Any, Any], ...]
    prompts: tuple[Prompt, ...]
    later: tuple[Contract[Any, Any], ...]
    publishes: tuple[Event, ...]
    remotes: tuple[Remote, ...]
    rule: str
    saves: bool
    when: Condition | None
    heavy: bool
    params: tuple[str, ...]
    source: str
    is_async: bool

    # 按参数判断步骤的种类：大模型、保存、读取、调用或纯计算。
    @property
    def kind(self) -> str:
        if "model" in self.params:
            return "model"
        if "remote" in self.params:
            return "remote"
        if self.saves:
            return "save"
        if "store" in self.params:
            return "read"
        if "call" in self.params:
            return "call"
        return "compute"


# 声明一个命名条件：只读取声明的字段，返回 True 时执行带这个条件的步骤。
def condition(title: str, *, reads: Sequence[str]) -> Callable[[Callable[[Any], bool]], Condition]:
    # 把条件函数包装成条件声明。
    def wrap(func: Callable[[Any], bool]) -> Condition:
        return Condition(func, func.__name__, title, tuple(reads), source_of(func))

    return wrap


# 声明一个步骤。
def step(
    title: str,
    *,
    reads: Sequence[str] = (),
    writes: Sequence[str] = (),
    uses: Sequence[Contract[Any, Any]] = (),
    prompts: Sequence[Prompt] = (),
    later: Sequence[Contract[Any, Any]] = (),
    publishes: Sequence[Event] = (),
    remotes: Sequence[Remote] = (),
    rule: str = "",
    saves: bool = False,
    when: Condition | None = None,
    heavy: bool = False,
) -> Callable[[Callable[..., Any]], Step]:
    # 把步骤函数包装成步骤声明。
    def wrap(func: Callable[..., Any]) -> Step:
        params = tuple(inspect.signature(func).parameters)
        return Step(
            func=func,
            name=func.__name__,
            title=title,
            reads=tuple(reads),
            writes=tuple(writes),
            uses=tuple(uses),
            prompts=tuple(prompts),
            later=tuple(later),
            publishes=tuple(publishes),
            remotes=tuple(remotes),
            rule=rule,
            saves=saves,
            when=when,
            heavy=heavy,
            params=params,
            source=source_of(func),
            is_async=inspect.iscoroutinefunction(func),
        )

    return wrap


# 返回函数所在的源码位置，写成“模块路径:行号”，不含磁盘绝对路径。
def source_of(func: Callable[..., Any]) -> str:
    path = func.__module__.replace(".", "/") + ".py"
    line = getattr(getattr(func, "__code__", None), "co_firstlineno", 0)
    return f"{path}:{line}"
