"""
组织列和数据库语句检查：访问带组织列的表必须明确限定为调用者的组织。
每一层查询（包括子查询、表别名、关联的表）都单独检查自己的条件；
无法证明隔离条件成立的语句一律拒绝执行，由存储实现改成简单语句。
"""

from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import Column, String, Table
from sqlalchemy.sql import Executable, operators, visitors
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


# 标记一个需要组织隔离的表列，供 Db 在执行前检查。
def org_column() -> Column[str]:
    return Column("org_id", String(64), nullable=False, index=True, info={"org_scoped": True})


# 对带组织列的表执行语句时，检查每一层查询的条件和写入的值。
def check_org(statement: Executable, caller: Caller) -> None:
    nodes = list(visitors.iterate(statement))  # type: ignore[arg-type]
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


# 一层查询中每个按组织隔离的来源都必须在这一层的条件中限定组织。
def check_select(select: Select[Any], org_id: str) -> set[Any]:
    sources = {source for source in flatten(select.get_final_froms()) if is_scoped(source)}
    for source in sources:
        if not guarded(select.whereclause, source.c.org_id, org_id):
            raise StepRuleBroken(f"访问 {name_of(source)} 时必须写明组织编号等于调用者的组织")
    return sources


# 插入的组织必须是调用者的组织；修改和删除必须限定组织，且不能改组织编号。
def check_change(statement: Insert | Update | Delete, org_id: str) -> None:
    table = statement.table
    if isinstance(statement, Insert):
        values = statement.compile().params
        found = [
            value for key, value in values.items() if key == "org_id" or key.startswith("org_id_m")
        ]
        if not found or any(value != org_id for value in found):
            raise StepRuleBroken(f"写入 {name_of(table)} 时组织编号必须是调用者的组织")
        return
    if not guarded(statement.whereclause, table.c.org_id, org_id):
        raise StepRuleBroken(f"修改或删除 {name_of(table)} 时必须写明组织编号等于调用者的组织")
    values = getattr(statement, "_values", None) or {}
    if any(getattr(key, "name", key) == "org_id" for key in values):
        raise StepRuleBroken(f"不能通过更新语句修改 {name_of(table)} 的组织编号")


# AND 中有一个组织条件即可；OR 的每个分支都必须有组织条件。
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


# 展开关联查询，得到参与查询的每个表或别名。
def flatten(froms: Iterable[FromClause]) -> Iterator[FromClause]:
    for item in froms:
        if isinstance(item, Join):
            yield from flatten((item.left, item.right))
        else:
            yield item


# 带组织列的表，或者这种表的别名。
def is_scoped(node: Any) -> bool:
    table = node.element if is_alias(node) else node
    return (
        isinstance(table, Table)
        and "org_id" in table.c
        and bool(table.c.org_id.info.get("org_scoped"))
    )


# 判断是否为某个表的别名（子查询不算）。
def is_alias(node: Any) -> bool:
    return isinstance(node, Alias) and isinstance(node.element, Table)


# 报错中使用的表名。
def name_of(source: Any) -> str:
    return str(getattr(source, "name", source))
