from dataclasses import dataclass
from typing import Literal

from shared.data.models import Data
from shared.db.budget import QueryBudget
from shared.errors.kinds import BusinessError


@dataclass(frozen=True, eq=False)
class Contract[In: Data, Out: Data]:
    name: str
    title: str
    input: type[In]
    output: type[Out]
    access: str
    errors: tuple[type[BusinessError], ...] = ()
    entry: bool = True
    timeout: float = 30.0
    audit: bool = False
    stream: bool = False

    aliases: tuple[str, ...] = ()
    query_budget: QueryBudget | None = None
    effect: Literal["query", "command"] | None = None

    @property
    def module(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def action(self) -> str:
        return self.name.split(".", 1)[-1]


def contract[In: Data, Out: Data](
    name: str,
    title: str,
    *,
    input: type[In],
    output: type[Out],
    access: str,
    errors: tuple[type[BusinessError], ...] = (),
    entry: bool = True,
    timeout: float = 30.0,
    audit: bool = False,
    stream: bool = False,
    aliases: tuple[str, ...] = (),
    query_budget: QueryBudget | None = None,
    effect: Literal["query", "command"] | None = None,
) -> Contract[In, Out]:
    return Contract(
        name,
        title,
        input,
        output,
        access,
        errors,
        entry,
        timeout,
        audit,
        stream,
        aliases=aliases,
        query_budget=query_budget,
        effect=effect,
    )
