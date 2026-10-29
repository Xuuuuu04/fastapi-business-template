from collections.abc import Callable, Iterable, Iterator
from typing import Any, cast

from sqlalchemy import Column, String, Table
from sqlalchemy.sql import ClauseElement, Executable, operators, visitors
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    ColumnClause,
)
from sqlalchemy.sql.selectable import Alias, FromClause, Join, Select

from shared.access.caller import Caller
from shared.errors.framework import NotAllowed, StepRuleBroken


def org_column() -> Column[str]:
    return Column("org_id", String(64), nullable=False, index=True, info={"org_scoped": True})


def check_org(statement: Executable, caller: Caller) -> None:
    nodes = list(visitors.iterate(cast(ClauseElement, statement)))
    owners = [node.table for node in nodes if isinstance(node, ColumnClause)]
    scoped = {node for node in [*nodes, *owners] if is_scoped(node)}
    if not scoped or caller.org_id == "*":
        return
    if not caller.org_id:
        raise NotAllowed("调用者没有组织编号，不能访问按组织隔离的数据")
    covered: set[Any] = set()
    for node in nodes:
        if isinstance(node, Select):
            covered |= check_select(node, caller.org_id)
    if isinstance(statement, Insert | Update | Delete) and is_scoped(statement.table):
        check_change(statement, caller.org_id)
        covered.add(statement.table)
    unchecked = scoped - covered - {source.element for source in covered if is_alias(source)}
    if unchecked:
        names = "、".join(sorted(str(getattr(item, "name", item)) for item in unchecked))
        raise StepRuleBroken(f"无法确认访问 {names} 时带有组织条件，请改成简单的单表或关联查询")


def check_select(
    select: Select[Any],
    org_id: str,
    column: str = "org_id",
    scoped: Callable[[Any], bool] | None = None,
    what: str = "组织编号等于调用者的组织",
) -> set[Any]:
    test = scoped or is_scoped
    sources = {source for source in flatten(select.get_final_froms()) if test(source)}
    for source in sources:
        if not guarded(select.whereclause, source.c[column], org_id):
            raise StepRuleBroken(f"访问 {name_of(source)} 时必须写明{what}")
    return sources


def check_change(
    statement: Insert | Update | Delete,
    org_id: str,
    column: str = "org_id",
    what: str = "组织编号",
) -> None:
    table = statement.table
    if isinstance(statement, Insert):
        values = statement.compile().params
        found = [
            value for key, value in values.items() if key == column or key.startswith(f"{column}_m")
        ]
        if not found or any(value != org_id for value in found):
            raise StepRuleBroken(f"写入 {name_of(table)} 时{what}必须是调用者自己")
        return
    if not guarded(statement.whereclause, table.c[column], org_id):
        raise StepRuleBroken(f"修改或删除 {name_of(table)} 时必须写明{what}等于调用者")
    values = getattr(statement, "_values", None) or {}
    if any(getattr(key, "name", key) == column for key in values):
        raise StepRuleBroken(f"不能通过更新语句修改 {name_of(table)} 的{what}")


def guarded(expr: Any, column: Any, org_id: str) -> bool:
    if isinstance(expr, BooleanClauseList):
        checks = [guarded(child, column, org_id) for child in expr.clauses]
        return all(checks) if expr.operator is operators.or_ else any(checks)
    if isinstance(expr, BinaryExpression) and expr.operator is operators.eq:
        pairs = ((expr.left, expr.right), (expr.right, expr.left))
        return any(
            left.compare(column) and isinstance(right, BindParameter) and right.value == org_id
            for left, right in pairs
        )
    return False


def flatten(froms: Iterable[FromClause]) -> Iterator[FromClause]:
    for item in froms:
        if isinstance(item, Join):
            yield from flatten((item.left, item.right))
        else:
            yield item


def is_scoped(node: Any) -> bool:
    table = node.element if is_alias(node) else node
    return (
        isinstance(table, Table)
        and "org_id" in table.c
        and bool(table.c.org_id.info.get("org_scoped"))
    )


def is_alias(node: Any) -> bool:
    return isinstance(node, Alias) and isinstance(node.element, Table)


def name_of(source: Any) -> str:
    return str(getattr(source, "name", source))
