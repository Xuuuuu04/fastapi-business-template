"""
按负责人隔离：没有 see_all 权限时每层查询都要限定负责人是自己，写入的负责人必须是自己，
不能改负责人；有 see_all 权限的调用者不受限制。
"""

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, func, insert, select, update

from shared.access.caller import Caller
from shared.db.owner import check_owner, owner_column
from shared.errors.framework import StepRuleBroken

probe = MetaData()
deals = Table(
    "owner_probe_deals",
    probe,
    Column("id", Integer, primary_key=True),
    owner_column(see_all="probe.manage"),
)
SALES = Caller("u7", "user", "销售", frozenset({"probe.read"}), "north")
BOSS = Caller("u1", "user", "主管", frozenset({"probe.manage"}), "north")


# 普通调用者必须限定负责人；子查询也要单独限定；主管不受限制。
def test_owner_conditions() -> None:
    mine = deals.c.owner_id == SALES.id
    check_owner(select(deals).where(mine), SALES)
    check_owner(insert(deals).values(id=1, owner_id=SALES.id), SALES)
    check_owner(update(deals).where(mine, deals.c.id == 1).values(id=2), SALES)
    for statement in (
        select(deals),
        select(deals).where(deals.c.owner_id == "u8"),
        insert(deals).values(id=1, owner_id="u8"),
        update(deals).where(mine).values(owner_id="u8"),
        select(deals).where(mine, deals.c.id.in_(select(func.max(deals.c.id)))),
    ):
        with pytest.raises(StepRuleBroken):
            check_owner(statement, SALES)
    check_owner(select(deals), BOSS)
    check_owner(update(deals).values(owner_id="u8"), BOSS)
