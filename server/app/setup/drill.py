"""
按实际Schedule入口在新数据库上跑完整流程，所有外部请求只回放原件，输出可审查阶段证据。
"""

import asyncio
import json
import shutil
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from app.setup.build import Services, build
from shared.config.settings import Settings
from shared.db.schema import head_revision
from shared.db.tables import metadata
from shared.drills.metrics import MemoryPeak, report
from shared.drills.replay import Replay, transports
from shared.jobs.schedule import Scheduler
from shared.jobs.worker import Worker, WorkerOptions
from shared.model_calls.providers import FakeModel
from shared.modules.module import Module
from shared.pipelines.tables import runs
from shared.remote_calls.remote import RemoteConfig


# 只使用演练自有文件/数据库/模拟模型，清空真实配置，不继承.env和服务密钥。
def settings_for(url: str, folder: Path, names: set[str]) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=url,
        api_keys=[],
        legacy_database_url="",
        file_storage="local",
        file_root=str(folder / "files"),
        upload_root=str(folder / "uploads"),
        run_records="memory",
        run_record_limit=10000,
        remotes={
            name: RemoteConfig(base_url="https://replay.invalid", max_response_bytes=256000000)
            for name in names
        },
        model_base_url="",
        model_api_key=None,
    )


# 可显式导入隔离库数据；表必须来自模块登记，JSONL按批加载，不读取真实业务库。
async def seed(services: Services, config: dict[str, Any], root: Path) -> None:
    from sqlalchemy import insert

    tables = {
        table.name: table for module in services.catalog.modules.values() for table in module.tables
    }
    for item in config.get("seed", []):
        if item["table"] not in tables:
            raise ValueError("seed只能写入已登记业务表")
        path = (root / item["file"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("seed文件超出演练目录")
        await load_seed(services, insert(tables[item["table"]]), path)


# 一张表独立分批导入，事务只覆盖一个批次。
async def load_seed(services: Services, statement: Any, path: Path) -> None:
    batch = []
    with path.open() as source:
        for line in source:
            batch.append(json.loads(line))
            if len(batch) == 5000:
                async with services.database.write() as connection:
                    await connection.execute(statement, batch)
                batch.clear()
    if batch:
        async with services.database.write() as connection:
            await connection.execute(statement, batch)


# 建表只发生在刚创建的新文件/schema，迁移版本标明当前演练框架。
async def prepare(services: Services) -> None:
    groups = {id(metadata): metadata}
    for module in services.catalog.modules.values():
        for table in module.tables:
            groups[id(table.metadata)] = table.metadata
    async with services.database.write() as connection:
        for group in groups.values():
            await connection.run_sync(group.create_all)
        await connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await connection.execute(
            text("INSERT INTO alembic_version VALUES (:head)"), {"head": head_revision()}
        )


# 真实规模输入由业务Schedule或seed声明，框架不把规模数字当已处理行数。
async def execute(
    modules: Sequence[Module],
    config: dict[str, Any],
    url: str,
    folder: Path,
    source_root: Path,
    output: Path,
) -> dict[str, Any]:
    names = {remote.name for module in modules for remote in module.remotes}
    built = build(settings_for(url, folder, names), modules=modules, provider=FakeModel())
    replay = transports(config.get("replay", {}), source_root, names)
    if built.remotes is not None:
        built.remotes.transports = {name: transport for name, transport in replay.items()}
    memory = MemoryPeak()
    sampler = asyncio.create_task(memory.sample())
    started = time.perf_counter()
    try:
        await prepare(built)
        await seed(built, config, source_root)
        run_id, manual, state = await scheduled(built, config)
        stages = await report(built.database, built.recorder, run_id)
        coverage = covered(stages, replay, built)
        output.mkdir(parents=True, exist_ok=True)
        files = Path(built.settings.file_root)
        if files.exists():
            await asyncio.to_thread(
                shutil.copytree, files, output / "artifacts", dirs_exist_ok=True
            )
        result = dict(
            pipeline=config["pipeline"],
            run_id=run_id,
            state=state,
            needs_manual=manual,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            requested_scale=config.get("scale"),
            stages=stages,
            coverage=coverage,
            isolated=True,
            external_network=False,
        )
    finally:
        memory.stop.set()
        await sampler
        await built.close()
    result["memory_peak_bytes"] = memory.peak
    result["memory_evidence"] = "进程RSS每20ms采样；框架及本次运行共同内存，不等于操作系统精确峰值"
    (output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# 只选择本流程的实际定时入口，Worker完成后才报告成功；等待超时明确需要人工。
async def scheduled(services: Services, config: dict[str, Any]) -> tuple[str, bool, str]:
    pipeline = services.catalog.pipelines.get(config["pipeline"])
    if pipeline is None:
        raise ValueError("演练流程没有登记")
    schedules = [
        schedule for schedule in services.catalog.schedules if schedule.contract is pipeline.start
    ]
    if len(schedules) != 1:
        raise ValueError("演练需要一个明确的流程Schedule首入口")
    org = config.get("org_id", "drill")
    period = float(config.get("period", time.time()))
    scheduler = Scheduler(
        [replace(schedules[0], org_ids=(org,))], services.queue, services.database, org
    )
    await scheduler.tick(period)
    async with services.database.read() as connection:
        row = (
            (await connection.execute(select(runs).where(runs.c.pipeline == pipeline.name)))
            .mappings()
            .one()
        )
        run_id = row["id"]
    worker = Worker(services.runtime, services.queue, [], WorkerOptions())
    try:
        async with asyncio.timeout(config.get("timeout_seconds", 300)):
            while True:
                await services.queue.pipelines.reconcile()
                async with services.database.read() as connection:
                    state = await connection.scalar(select(runs.c.state).where(runs.c.id == run_id))
                if state in (
                    "succeeded",
                    "failed",
                    "unknown",
                    "version_blocked",
                    "overdue_paused",
                    "skipped",
                ):
                    return run_id, state != "succeeded", str(state)
                ticket = await services.queue.claim(time.time())
                if ticket:
                    await worker.execute(ticket)
                else:
                    await asyncio.sleep(0.01)
    except TimeoutError:
        return run_id, True, "timed_out"


# 回放覆盖来自实际远程运行记录，不从清单存在推测已覆盖阶段。
def covered(
    stages: list[dict[str, Any]], replay: dict[str, Replay], services: Services
) -> dict[str, Any]:
    used = [item for transport in replay.values() for item in transport.used]
    roots = getattr(services.recorder.store, "rows", {})
    for stage in stages:
        records = [roots[run_id] for run_id in stage["run_ids"] if run_id in roots]
        stage["replay"] = any(part.remotes for run in records for part in run.steps)
    return dict(
        originals=used,
        replay_stages=[stage["name"] for stage in stages if stage["replay"]],
        no_replay_stages=[stage["name"] for stage in stages if not stage["replay"]],
        uncovered_stages=[stage["name"] for stage in stages if stage["state"] != "succeeded"],
        model_calls="模拟模型，不证明真实模型结果",
        schema="登记表create_all，不代替真实迁移/恢复检查",
    )
