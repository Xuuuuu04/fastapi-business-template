"""
迟到回执、重复确认与账号切换的持久证据，用实际条件更新验证恢复不会覆盖新状态。
"""

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select

from shared.access.caller import SYSTEM
from shared.effects.service import binding_of
from shared.effects.spec import AdapterReply
from shared.effects.tables import attempts
from shared.errors.framework import StepRuleBroken
from tests.framework.test_provider_effects import Input, Output, service_at

pytestmark = pytest.mark.anyio


# 迟到的旧回执只能追加证据，不能把已经完成的新尝试覆盖成拒绝。
async def test_late_receipt_preserves_new_attempt(tmp_path: Path) -> None:
    service, original, adapter, database = await service_at(tmp_path)
    spec = replace(original, repeat_safe=True)
    try:
        async with database.write() as connection:
            id = await service.store.prepare(
                connection,
                spec,
                SYSTEM,
                "late",
                Input(message="body").model_dump_json(),
                True,
                0,
                binding_of(adapter),
            )
        old = await service.store.claim(id, spec, 1, lookup=False)
        new = await service.store.claim(id, spec, 100, lookup=False)
        assert old == 1 and new == 2
        assert await service.store.save(
            id, new, AdapterReply("completed", Output(reference="new"), "new"), 101
        )
        assert not await service.store.save(
            id, old, AdapterReply("refused", external_id="old"), 102
        )
        row = await service.store.read(id, SYSTEM)
        assert row["state"] == "completed" and row["external_id"] == "new"
        async with database.read() as connection:
            history = (
                (await connection.execute(select(attempts).where(attempts.c.intent_id == id)))
                .mappings()
                .all()
            )
        assert any(item["attempt"] == old and item["external_id"] == "old" for item in history)
    finally:
        await database.close()


# 供应商账号切换后，旧意图不能被新账号继续发送或查证。
async def test_adapter_account_change_rejects_old_intent(tmp_path: Path) -> None:
    service, spec, adapter, database = await service_at(tmp_path)
    try:
        result = await service.call(spec, Input(message="body"), SYSTEM, "one", [], [])
        adapter.identity = "another-account"
        with pytest.raises(StepRuleBroken, match="账号或连接目标"):
            await service.perform(result.id, SYSTEM, [], [], lookup=True)
        assert adapter.sent == 1
    finally:
        await database.close()
