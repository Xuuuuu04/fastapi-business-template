"""
内置运维端到端验收：真实备份隔离恢复ready、分段保留、容量暂停与Webhook失败事实。
"""

import json
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import insert, select, update

from app.setup.build import build
from app.setup.drill import prepare
from shared.access.audit import audit_records
from shared.access.caller import SYSTEM
from shared.config.settings import Settings
from shared.drills.isolation import isolated
from shared.jobs.schedule import Scheduler
from shared.jobs.tables import jobs, segments
from shared.jobs.worker import Worker, WorkerOptions
from shared.operations.config import OperationsConfig
from shared.operations.module import Input, backup_op, capacity_op, notify_op
from shared.operations.notifications import Webhook
from shared.operations.tables import state
from shared.pipelines.tables import notifications
from shared.records.stores import RunFilter
from tests.framework.operations_sample import Input as SampleInput
from tests.framework.operations_sample import critical, module, optional

pytestmark = pytest.mark.anyio


# 两库测试都在本任务的新空间，真实备份不修改外部业务库。
def settings(url: str, root: Path, **options) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=url,
        file_root=str(root / "files"),
        upload_root=str(root / "uploads"),
        operations=OperationsConfig(backup_root=str(root / "backups"), **options),
    )


# 按定时计划登记后逐个执行，运维任务真实进入运行记录与计算图。
async def scheduled(services, now: float) -> None:
    scheduler = Scheduler(services.catalog.schedules, services.queue, services.database)
    await scheduler.tick(now)
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    while ticket := await services.queue.claim(time.time()):
        await worker.execute(ticket)


# 每次备份真实恢复并ready；验证文件内容、行数、迁移与清理范围。
async def test_scheduled_backup_restores_and_checks_ready(tmp_path: Path) -> None:
    postgres = os.environ.get("APP_TEST_DATABASE_URL", "")
    async with isolated(tmp_path, postgres if postgres.startswith("postgresql") else "") as url:
        built = build(settings(url, tmp_path, backup=True), modules=[module])
        try:
            await prepare(built)
            files = tmp_path / "files/ops_sample"
            files.mkdir(parents=True)
            (files / "original.json").write_text('{"original": true}')
            await scheduled(built, time.time())
            archives = list((tmp_path / "backups").glob("backup-*"))
            assert len(archives) == 1
            verified = json.loads((archives[0] / "verified.json").read_text())
            assert all(verified[key] for key in ("ready", "rows", "migration", "files"))
            assert (
                archives[0] / "restored_files/ops_sample/original.json"
            ).read_text() == '{"original": true}'
            manifest = json.loads((archives[0] / "manifest.json").read_text())
            assert manifest["rows"]["alembic_version"] == 1
            assert "system_ops_state" in manifest["rows"]
            runs = await built.recorder.recent(RunFilter(), 10)
            assert any(run.contract == backup_op.name for run in runs)
        finally:
            await built.close()


# 构造过期历史和必须保留的待确认任务。
async def retention_seed(built) -> tuple[str, str]:
    async with built.database.write() as conn:
        for index in range(7):
            await conn.execute(
                insert(audit_records).values(
                    id=str(index),
                    actor="system",
                    org_id="*",
                    contract="old",
                    status="ok",
                    request_id="",
                    run_id="",
                    created_at=0,
                )
            )
        unknown = await built.queue.submit(
            conn, critical, SampleInput(), SYSTEM, key="unknown", request_id=""
        )
        done = await built.queue.submit(
            conn, critical, SampleInput(), SYSTEM, key="done", request_id=""
        )
        await conn.execute(
            update(jobs).where(jobs.c.id == unknown).values(state="unknown", finished_at=0)
        )
        await conn.execute(
            update(jobs).where(jobs.c.id == done).values(state="done", finished_at=0)
        )
    return unknown, done


# 500行以下批量同样走Checkpoint，不删除待确认任务或正式文件。
async def test_segmented_retention_protects_confirmation_and_files(tmp_path: Path) -> None:
    postgres = os.environ.get("APP_TEST_DATABASE_URL", "")
    async with isolated(tmp_path, postgres if postgres.startswith("postgresql") else "") as url:
        built = build(
            settings(
                url,
                tmp_path,
                retention=True,
                batch_size=2,
                original_prefixes=["ops_sample/originals"],
            ),
            modules=[module],
        )
        try:
            await prepare(built)
            unknown, done = await retention_seed(built)
            originals = tmp_path / "files/ops_sample/originals"
            originals.mkdir(parents=True)
            (originals / "old").write_text("old")
            os.utime(originals / "old", (0, 0))
            protected = tmp_path / "files/ops_sample/protected"
            protected.write_text("keep")
            os.utime(protected, (0, 0))
            await scheduled(built, time.time())
            async with built.database.read() as conn:
                assert (
                    await conn.scalar(select(jobs.c.state).where(jobs.c.id == unknown)) == "unknown"
                )
                assert await conn.scalar(select(jobs.c.id).where(jobs.c.id == done)) is None
                assert not (
                    await conn.scalars(
                        select(audit_records.c.id).where(audit_records.c.created_at == 0)
                    )
                ).all()
                assert len((await conn.scalars(select(segments.c.number))).all()) >= 8
            assert not (originals / "old").exists() and protected.exists()
        finally:
            await built.close()


# 超阈值只暂停非关键下一次领取，关键任务继续，恢复后解除。
async def test_capacity_pause_is_shared_and_reversible(tmp_path: Path) -> None:
    async with isolated(tmp_path, os.environ.get("APP_TEST_DATABASE_URL", "")) as url:
        config = settings(url, tmp_path, capacity=True, database_bytes=1, pause_noncritical=True)
        built = build(config, modules=[module])
        try:
            await prepare(built)
            await built.runtime.run(capacity_op, Input(), caller=SYSTEM)
            async with built.database.write() as conn:
                optional_id = await built.queue.submit(
                    conn, optional, SampleInput(), SYSTEM, key="optional", request_id=""
                )
                critical_id = await built.queue.submit(
                    conn, critical, SampleInput(), SYSTEM, key="critical", request_id=""
                )
            other = build(config, modules=[module])
            try:
                ticket = await other.queue.claim(time.time())
                assert ticket and ticket.id == critical_id
                assert await other.queue.claim(time.time()) is None
                built.settings.operations.database_bytes = 10**15
                built.settings.operations.disk_percent = 100
                await built.runtime.run(capacity_op, Input(), caller=SYSTEM)
                ticket = await other.queue.claim(time.time())
                assert ticket and ticket.id == optional_id
            finally:
                await other.close()
            async with built.database.read() as conn:
                assert await conn.scalar(select(state.c.paused)) is False
                assert len((await conn.scalars(select(notifications.c.id))).all()) == 1
        finally:
            await built.close()


# HTTP或平台失败不标sent，重试能成功；待确认提醒按任务编号去重。
async def test_webhook_failure_retry_and_confirmation(tmp_path: Path, monkeypatch) -> None:
    delivered = []

    # 明确失败不访问真实平台，第二次使用相同pending。
    async def send(self, payload):
        delivered.append(payload)
        if len(delivered) == 1:
            raise ValueError("平台拒绝")

    monkeypatch.setattr(Webhook, "send", send)
    async with isolated(tmp_path, os.environ.get("APP_TEST_DATABASE_URL", "")) as url:
        built = build(
            settings(
                url, tmp_path, notifications=True, webhook_url="https://example.invalid/secret"
            ),
            modules=[module],
        )
        try:
            await prepare(built)
            async with built.database.write() as conn:
                job = await built.queue.submit(
                    conn, critical, SampleInput(), SYSTEM, key="unknown", request_id=""
                )
                await conn.execute(update(jobs).where(jobs.c.id == job).values(state="unknown"))
            await built.runtime.run(notify_op, Input(), caller=SYSTEM)
            async with built.database.read() as conn:
                assert await conn.scalar(select(notifications.c.state)) == "pending"
            await built.runtime.run(notify_op, Input(), caller=SYSTEM)
            async with built.database.read() as conn:
                row = (await conn.execute(select(notifications))).mappings().one()
                assert row["state"] == "sent" and row["attempt"] == 2
                assert "secret" not in row["payload_json"]
        finally:
            await built.close()


# 三类Webhook包装与平台拒绝采用真实传输协议，只替换网络为本地MockTransport。
@pytest.mark.parametrize("style", ["generic", "wecom", "feishu"])
async def test_webhook_wire_format_and_platform_error(style: str, monkeypatch) -> None:
    import httpx2

    from shared.operations import notifications as sender

    payload = {"kind": "capacity", "key": "today", "details": {"bytes": 100}}
    requests = []

    # HTTP200但平台明确拒绝时，send必须失败。
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json={"errcode": 1})

    client = httpx2.AsyncClient
    monkeypatch.setattr(
        sender.httpx2,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx2.MockTransport(respond), **kwargs),
    )
    webhook = Webhook(
        OperationsConfig(webhook_url="https://example.invalid/secret", webhook_format=style)
    )
    with pytest.raises(ValueError, match="拒绝"):
        await webhook.send(payload)
    if style == "generic":
        assert requests == [payload]
    else:
        assert "today" in json.dumps(requests[0])
        assert "secret" not in json.dumps(requests[0])


# 归档清理只删除验证成功且超期的自身归档，保留失败与未超期。
def test_archive_retention_only_expires_verified(tmp_path: Path) -> None:
    from shared.operations.backup import expire

    for name in ("backup-expired", "backup-failed", "backup-fresh"):
        (tmp_path / name).mkdir()
    (tmp_path / "backup-expired/verified.json").write_text("{}")
    (tmp_path / "backup-fresh/verified.json").write_text("{}")
    os.utime(tmp_path / "backup-expired", (0, 0))
    os.utime(tmp_path / "backup-failed", (0, 0))
    expire(tmp_path, 30)
    assert not (tmp_path / "backup-expired").exists()
    assert (tmp_path / "backup-failed").exists() and (tmp_path / "backup-fresh").exists()


# 迁移版本错误导致真实恢复ready失败，并登记备份失败而非可用归档。
async def test_backup_bad_revision_is_not_verified(tmp_path: Path) -> None:
    async with isolated(tmp_path, os.environ.get("APP_TEST_DATABASE_URL", "")) as url:
        built = build(settings(url, tmp_path, backup=True), modules=[module])
        try:
            await prepare(built)
            from sqlalchemy import text

            async with built.database.write() as conn:
                await conn.execute(text("UPDATE alembic_version SET version_num='wrong'"))
            result = await built.runtime.run(backup_op, Input(), caller=SYSTEM)
            assert result.details["verified"] is False
            assert not list((tmp_path / "backups").glob("*/verified.json"))
            async with built.database.read() as conn:
                assert await conn.scalar(select(notifications.c.kind)) == "backup_failed"
        finally:
            await built.close()
