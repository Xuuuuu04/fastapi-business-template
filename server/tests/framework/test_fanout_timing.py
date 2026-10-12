"""
等待边界与主机延迟分开验证：真实超时必须失败，合成上游不受机器负载影响。
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from app.setup.build import Services
from shared.jobs.tables import jobs
from shared.jobs.worker import Worker, WorkerOptions
from shared.pipelines.tables import members
from tests.failure_reports import FAILURE_FILE, FINISHED, save_finished_runs
from tests.framework import fanout_driver
from tests.framework.fanout_driver import drain, fanout, now, start
from tests.framework.fanout_sample import Store, polls
from tests.framework.pipeline_reports import save_failed_pipeline

pytestmark = pytest.mark.anyio
__all__ = ["fanout"]


# 明确执行选择、规划、提交三个短阶段，随后只剩一个等待成员。
async def waiting(services: Services) -> tuple[str, dict]:
    run_id = await start(services, 1)
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    for _ in range(3):
        ticket = await services.queue.claim(now())
        assert ticket is not None
        await worker.execute(ticket)
    async with services.database.read() as connection:
        member = (await connection.execute(select(members))).mappings().one()
    assert member["phase_name"] == "ready"
    return run_id, dict(member)


# 重演宿主机超过20秒的停顿；只推进声明的轮询间隔，不能消耗合成等待预算。
async def test_host_delay_does_not_expire_synthetic_wait(fanout: Services, monkeypatch) -> None:
    run_id, member = await waiting(fanout)
    monkeypatch.setattr(fanout_driver, "wall_time", lambda: member["wait_until"] + 21)
    assert fanout_driver.wall_time() > member["wait_until"]
    root = await drain(fanout, run_id)
    assert root["state"] == "succeeded", root["reason"]
    assert now() < member["wait_until"]
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(polls)) == 2


# 到期前和提交时分别检查，保留原20秒期限，不能靠受控时钟掩盖超时。
@pytest.mark.parametrize("boundary", ["prepare", "commit"])
async def test_member_deadline_is_enforced(fanout: Services, monkeypatch, boundary) -> None:
    run_id, member = await waiting(fanout)
    clock = fanout.queue.clock
    if boundary == "prepare":
        clock.advance_to(member["wait_until"])
    else:
        original = Store.poll

        # SQL已写后才到期，完成检查必须撤销本次轮询。
        async def expired(self, data):
            result = await original(self, data)
            clock.advance_to(member["wait_until"])
            return result

        monkeypatch.setattr(Store, "poll", expired)
    root = await drain(fanout, run_id)
    assert root["state"] == "failed"
    async with fanout.database.read() as connection:
        assert "等待超时" in await connection.scalar(select(members.c.error))
        assert await connection.scalar(select(func.count()).select_from(polls)) == 0


# 租约重领保留等待截止时间，旧尝试不得写入，新尝试能正常完成。
async def test_member_expired_attempt_cannot_commit(fanout: Services) -> None:
    run_id, member = await waiting(fanout)
    old = await fanout.queue.claim(now())
    assert old is not None
    async with fanout.database.write() as connection:
        await connection.execute(
            update(jobs).where(jobs.c.id == old.id).values(lease_until=now() - 1)
        )
    assert await fanout.queue.reclaim(now()) == 1
    worker = Worker(fanout.runtime, fanout.queue, [], WorkerOptions())
    await worker.execute(old)
    async with fanout.database.read() as connection:
        assert await connection.scalar(select(func.count()).select_from(polls)) == 0
        assert await connection.scalar(select(members.c.wait_until)) == member["wait_until"]
    assert (await drain(fanout, run_id))["state"] == "succeeded"


# 执行前拒绝时所有操作都成功，仍保存完整运行和成员失败原因，不保存正文。
async def test_failure_snapshot_includes_pre_execution_rejection(
    fanout: Services, request, tmp_path: Path
) -> None:
    run_id, member = await waiting(fanout)
    fanout.queue.clock.advance_to(member["wait_until"])
    assert (await drain(fanout, run_id))["state"] == "failed"
    assert all(run.status == "ok" for run in FINISHED)
    path = save_finished_runs(tmp_path, request.node.nodeid, FINISHED)
    request.node.stash[FAILURE_FILE] = path
    await save_failed_pipeline(request.node, fanout.database)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["runs"]) == len(data["reports"]) == 3
    assert all("caller" not in run for run in data["runs"])
    assert all(run.caller not in path.read_text() for run in FINISHED if run.caller)
    row = data["pipeline_snapshot"]["pipeline_members"][0]
    assert row["state"] == "failed" and "等待超时" in row["error"]
    for rows in data["pipeline_snapshot"].values():
        for row in rows:
            assert not {"caller_json", "input_json", "output_json", "result_json"} & row.keys()


# PostgreSQL两次真实业务提交同时到达成员汇合，不能重复派发或丢掉成功结果。
@pytest.mark.postgres_only
async def test_concurrent_member_commits_and_reconcile(fanout: Services, monkeypatch) -> None:
    import asyncio

    original = Store.collect
    entered = 0
    ready = asyncio.Event()

    # 在业务SQL之后同步两个成员，实际数据库连接和提交仍由框架完成。
    async def together(self, id, version):
        nonlocal entered
        result = await original(self, id, version)
        entered += 1
        if entered == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=5)
        return result

    run_id = await start(fanout, 2)
    worker = Worker(fanout.runtime, fanout.queue, [], WorkerOptions())
    for _ in range(2):
        ticket = await fanout.queue.claim(now())
        assert ticket is not None
        await worker.execute(ticket)
    monkeypatch.setattr(Store, "collect", together)
    tickets = [await fanout.queue.claim(now()) for _ in range(2)]
    assert all(tickets)
    await asyncio.wait_for(
        asyncio.gather(*(worker.execute(ticket) for ticket in tickets)), timeout=10
    )
    await asyncio.gather(fanout.queue.pipelines.reconcile(), fanout.queue.pipelines.reconcile())
    assert (await drain(fanout, run_id))["state"] == "succeeded"
    async with fanout.database.read() as connection:
        assert (
            await connection.scalar(
                select(func.count()).select_from(members).where(members.c.accepted.is_(True))
            )
            == 2
        )
