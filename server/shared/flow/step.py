import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from shared.effects.spec import ProviderSpec
from shared.model_calls.prompt import Prompt
from shared.modules.contract import Contract
from shared.remote_calls.endpoint import Endpoint
from shared.remote_calls.remote import Remote

PARAMS = (
    "data",
    "store",
    "call",
    "model",
    "remote",
    "cache",
    "later",
    "caller",
    "note",
    "emit",
    "checkpoint",
    "pipeline",
    "effects",
    "clock",
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
    remotes: tuple[Remote, ...]
    rule: str
    saves: bool
    when: Condition | None
    heavy: bool
    params: tuple[str, ...]
    source: str
    is_async: bool
    endpoints: tuple[Endpoint[Any, Any], ...] = ()
    calcs: tuple[Callable[..., Any], ...] = ()
    providers: tuple[ProviderSpec, ...] = ()
    observes: tuple[str, ...] = ()
    simulated: bool = False

    @property
    def kind(self) -> str:
        if "model" in self.params:
            return "model"
        if "remote" in self.params or "effects" in self.params:
            return "remote"
        if self.saves:
            return "save"
        if "store" in self.params:
            return "read"
        if "call" in self.params:
            return "call"
        return "compute"


def condition(title: str, *, reads: Sequence[str]) -> Callable[[Callable[[Any], bool]], Condition]:
    def wrap(func: Callable[[Any], bool]) -> Condition:
        return Condition(func, func.__name__, title, tuple(reads), source_of(func))

    return wrap


def step(
    title: str,
    *,
    reads: Sequence[str] = (),
    writes: Sequence[str] = (),
    uses: Sequence[Contract[Any, Any]] = (),
    prompts: Sequence[Prompt] = (),
    later: Sequence[Contract[Any, Any]] = (),
    remotes: Sequence[Remote] = (),
    endpoints: Sequence[Endpoint[Any, Any]] = (),
    rule: str = "",
    saves: bool = False,
    when: Condition | None = None,
    heavy: bool = False,
    calcs: Sequence[Callable[..., Any]] = (),
    providers: Sequence[ProviderSpec] = (),
    observes: Sequence[str] = (),
    simulated: bool = False,
) -> Callable[[Callable[..., Any]], Step]:
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
            remotes=tuple(remotes),
            endpoints=tuple(endpoints),
            rule=rule,
            saves=saves,
            when=when,
            heavy=heavy,
            params=params,
            source=source_of(func),
            is_async=inspect.iscoroutinefunction(func),
            calcs=tuple(calcs),
            providers=tuple(providers),
            observes=tuple(observes),
            simulated=simulated,
        )

    return wrap


def source_of(func: Callable[..., Any]) -> str:
    path = func.__module__.replace(".", "/") + ".py"
    line = getattr(getattr(func, "__code__", None), "co_firstlineno", 0)
    return f"{path}:{line}"
