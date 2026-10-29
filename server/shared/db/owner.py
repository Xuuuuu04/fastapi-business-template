"""
按负责人隔离的数据（行级权限）：表用 owner_column(see_all=权限名) 声明负责人列。
没有 see_all 权限的调用者，每一层查询都必须写明“负责人等于调用者本人”，写入的负责人必须是自己，
不能改负责人；有这个权限的调用者（例如主管）不受限制。检查方式与组织隔离相同。
"""

from typing import Any, cast

from sqlalchemy import Column, String, Table
from sqlalchemy.sql import ClauseElement, Executable, visitors
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.selectable import Select

from shared.access.caller import Caller
from shared.db.org import check_change, check_select, is_alias, name_of
from shared.errors.framework import StepRuleBroken

WHAT = "负责人等于调用者本人"


# 标记负责人列；拥有 see_all 权限的调用者可以看到和修改全部记录。
def owner_column(see_all: str) -> Column[str]:
    return Column(
        "owner_id",
        String(64),
        nullable=False,
        index=True,
        info={"owner_scoped": True, "see_all": see_all},
    )


# 对按负责人隔离、且调用者没有 see_all 权限的表，检查每一层查询的条件和写入的值。
def check_owner(statement: Executable, caller: Caller) -> None:
    nodes = list(visitors.iterate(cast(ClauseElement, statement)))
    owners = [node.table for node in nodes if isinstance(node, ColumnClause)]

    # 只检查调用者不能看全部的表。
    def limited(node: Any) -> bool:
        table = node.element if is_alias(node) else node
        if not isinstance(table, Table) or "owner_id" not in table.c:
            return False
        info = table.c.owner_id.info
        return bool(info.get("owner_scoped")) and not caller.can(str(info.get("see_all")))

    scoped = {node for node in [*nodes, *owners] if limited(node)}
    if not scoped:
        return
    covered: set[Any] = set()
    for node in nodes:
        if isinstance(node, Select):
            covered |= check_select(node, caller.id, "owner_id", limited, WHAT)
    if isinstance(statement, Insert | Update | Delete) and limited(statement.table):
        check_change(statement, caller.id, "owner_id", "负责人")
        covered.add(statement.table)
    unchecked = scoped - covered - {source.element for source in covered if is_alias(source)}
    if unchecked:
        names = "、".join(sorted(name_of(item) for item in unchecked))
        raise StepRuleBroken(f"无法确认访问 {names} 时带有负责人条件，请改成简单的单表或关联查询")
