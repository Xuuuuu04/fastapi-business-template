"""
磁盘和数据库容量观察，超阈值共享暂停非关键任务，恢复后自动解除。
"""

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import make_url

from shared.db.access import Db
from shared.jobs.tables import jobs
from shared.operations.notifications import enqueue
from shared.operations.tables import state


# 旧队列不查询运维表；开启后跨worker使用共享暂停条件。
async def capacity_filter(queue: Any, connection: Any, pick: Any) -> Any:
    if not queue.capacity_enabled:
        return pick
    paused = await connection.scalar(select(state.c.paused).where(state.c.name == "capacity"))
    if paused:
        allowed = [name for name, plan in queue.catalog.plans.items() if plan.critical]
        return pick.where(jobs.c.contract.in_(allowed))
    return pick


# 目录未创建时检查其最近存在父目录所在磁盘。
def disk_usage(path: str) -> float:
    folder = Path(path).resolve()
    while not folder.exists():
        folder = folder.parent
    disk = shutil.disk_usage(folder)
    return disk.used / disk.total * 100


# 容量来源明确：PG整库实际大小，SQLite文件与WAL；不把未知当零。
async def observe(db: Db, settings: Any) -> dict[str, Any]:
    url = make_url(settings.database_url)
    if url.get_backend_name() == "postgresql":
        row = await db.one(select(func.pg_database_size(func.current_database()).label("bytes")))
        size = int(row["bytes"])
    else:
        path = Path(url.database or "")
        size = sum(
            item.stat().st_size for item in (path, Path(str(path) + "-wal")) if item.is_file()
        )
    percentages = await asyncio.gather(
        *(
            asyncio.to_thread(disk_usage, path)
            for path in (settings.file_root, settings.upload_root, settings.operations.backup_root)
        )
    )
    config = settings.operations
    exceeded = max(percentages) >= config.disk_percent or bool(
        config.database_bytes and size >= config.database_bytes
    )
    return dict(database_bytes=size, disk_percent=max(percentages), exceeded=exceeded)


# 状态与提醒一起提交，所有worker在领取下一任务时读取同一事实。
async def save(db: Db, settings: Any, result: dict[str, Any]) -> None:
    now = time.time()
    values = dict(
        paused=result["exceeded"] and settings.operations.pause_noncritical,
        observed_at=now,
        body=json.dumps(result),
    )
    old = await db.first(select(state).where(state.c.name == "capacity").with_for_update())
    if old is None:
        await db.change(insert(state).values(name="capacity", **values))
    else:
        await db.change(update(state).where(state.c.name == "capacity").values(**values))
    if result["exceeded"]:
        await enqueue(db, "capacity", str(int(now // 86400)), result)
