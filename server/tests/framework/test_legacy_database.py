"""
验证存储实现通过 legacy 参数读取旧库，写入旧库时被只读入口拒绝。
"""

from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String, Table, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.setup.build import build
from legacy.schema import legacy_metadata
from shared.access.caller import SYSTEM
from shared.errors.framework import StepRuleBroken
from shared.model_calls.providers import FakeModel
from shared.public import Data, Db, Flow, Module, Nothing, WorkData, contract, meaning, step
from tests.testing_app import make_settings, reset_database

old_items = Table(
    "old_items",
    legacy_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(40), nullable=False),
)


class OldItem(Data):
    name: str = meaning("旧系统中的名称")


class OldWork(WorkData):
    result: OldItem = meaning("从旧库读取的结果")


class OldStore:
    # 旧库入口由构造参数名 legacy 注入。
    def __init__(self, legacy: Db) -> None:
        self.legacy = legacy

    # 按编号读取旧库数据。
    async def read(self) -> str:
        row = await self.legacy.first(select(old_items.c.name).where(old_items.c.id == 1))
        assert row is not None
        return str(row["name"])

    # 尝试修改旧库，用于检查只读保护。
    async def write(self) -> None:
        await self.legacy.change(insert(old_items).values(id=2, name="不应写入"))


read_old = contract("legacy_probe.read", "读旧库", input=Nothing, output=OldItem, access="public")
write_old = contract(
    "legacy_probe.write", "试写旧库", input=Nothing, output=OldItem, access="public"
)


# 从独立旧库读取并写入流程结果。
@step("读取旧库", writes=["result"])
async def read_item(data: OldWork, store: OldStore) -> None:
    data.result = OldItem(name=await store.read())


# 尝试经 legacy 入口写入，预期被拒绝。
@step("试写旧库", writes=["result"])
async def write_item(data: OldWork, store: OldStore) -> None:
    await store.write()
    data.result = OldItem(name="错误")


probe = Module(
    "legacy_probe",
    "旧库测试",
    "1",
    {
        read_old: Flow("读旧库", work=OldWork, result="result", steps=[read_item]),
        write_old: Flow("试写旧库", work=OldWork, result="result", steps=[write_item]),
    },
    store=OldStore,
)


# 旧库表建立在独立数据库，新系统的元数据不包含它。
@pytest.mark.anyio
async def test_legacy_read_only(tmp_path: Path) -> None:
    old_url = f"sqlite+aiosqlite:///{tmp_path}/legacy.db"
    engine = create_async_engine(old_url)
    async with engine.begin() as connection:
        await connection.run_sync(legacy_metadata.create_all)
        await connection.execute(insert(old_items).values(id=1, name="旧名称"))
    await engine.dispose()

    settings = make_settings(tmp_path, legacy_database_url=old_url)
    await reset_database(settings.database_url)
    services = build(settings, modules=[probe], provider=FakeModel())
    try:
        found = await services.runtime.run(read_old, Nothing(), caller=SYSTEM)
        assert found.name == "旧名称"
        with pytest.raises(StepRuleBroken):
            await services.runtime.run(write_old, Nothing(), caller=SYSTEM)
    finally:
        await services.close()
