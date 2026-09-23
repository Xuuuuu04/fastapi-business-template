"""
运行记录的保存位置：进程内存或数据库。
内存保存有容量上限，超出时丢弃最早的记录并计数；数据库保存供多进程共同查询。
两种实现遵守同一个 RunStore 约定，查询接口不关心记录存在哪里。
"""

import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, insert, select

from shared.db.database import Database
from shared.records.models import RunRecord, run_from_dict
from shared.records.tables import run_records


@dataclass(frozen=True)
class RunFilter:
    module: str = ""
    contract: str = ""
    status: str = ""
    request_id: str = ""
    job_id: str = ""
    before: float | None = None
    top_only: bool = True


class RunStore(Protocol):
    immediate: bool
    dropped: int

    # 保存一批已经结束的运行记录。
    async def save(self, runs: list[RunRecord]) -> None: ...

    # 按运行编号读取一条记录。
    async def get(self, run_id: str) -> RunRecord | None: ...

    # 读取同一次最外层运行下的全部记录。
    async def tree(self, root_id: str) -> list[RunRecord]: ...

    # 按条件读取最近的记录，最新的在前。
    async def recent(self, rules: RunFilter, limit: int) -> list[RunRecord]: ...

    # 删除早于指定时间的记录，返回删除条数。
    async def clean(self, older_than: float) -> int: ...


class MemoryRunStore:
    immediate = True

    # 设置最多保存多少条运行记录。
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.rows: OrderedDict[str, RunRecord] = OrderedDict()
        self.dropped = 0

    # 保存记录，超出容量时丢弃最早的并计数。
    async def save(self, runs: list[RunRecord]) -> None:
        for run in runs:
            self.rows[run.id] = run
        while len(self.rows) > self.limit:
            self.rows.popitem(last=False)
            self.dropped += 1

    # 按运行编号读取一条记录。
    async def get(self, run_id: str) -> RunRecord | None:
        return self.rows.get(run_id)

    # 读取同一次最外层运行下的全部记录。
    async def tree(self, root_id: str) -> list[RunRecord]:
        return [run for run in self.rows.values() if run.root_id == root_id]

    # 按条件读取最近的记录。
    async def recent(self, rules: RunFilter, limit: int) -> list[RunRecord]:
        found = [run for run in reversed(self.rows.values()) if matches(run, rules)]
        return found[:limit]

    # 删除早于指定时间的记录。
    async def clean(self, older_than: float) -> int:
        old = [key for key, run in self.rows.items() if run.started_at < older_than]
        for key in old:
            del self.rows[key]
        return len(old)


# 判断一条内存记录是否符合查询条件。
def matches(run: RunRecord, rules: RunFilter) -> bool:
    checks = [
        not rules.module or run.module == rules.module,
        not rules.contract or run.contract == rules.contract,
        not rules.status or run.status == rules.status,
        not rules.request_id or run.request_id == rules.request_id,
        not rules.job_id or run.job_id == rules.job_id,
        rules.before is None or run.started_at < rules.before,
        not rules.top_only or not run.parent_id,
    ]
    return all(checks)


class SqlRunStore:
    immediate = False

    # 使用框架的数据库连接池保存记录。
    def __init__(self, database: Database) -> None:
        self.database = database
        self.dropped = 0

    # 在一个短事务中批量写入记录。
    async def save(self, runs: list[RunRecord]) -> None:
        if not runs:
            return
        rows = [to_row(run) for run in runs]
        async with self.database.write() as connection:
            await connection.execute(insert(run_records), rows)

    # 按运行编号读取一条记录。
    async def get(self, run_id: str) -> RunRecord | None:
        query = select(run_records.c.body).where(run_records.c.id == run_id)
        async with self.database.read() as connection:
            body = await connection.scalar(query)
        return None if body is None else run_from_dict(json.loads(body))

    # 读取同一次最外层运行下的全部记录。
    async def tree(self, root_id: str) -> list[RunRecord]:
        query = select(run_records.c.body).where(run_records.c.root_id == root_id)
        async with self.database.read() as connection:
            bodies = (await connection.scalars(query.order_by(run_records.c.started_at))).all()
        return [run_from_dict(json.loads(body)) for body in bodies]

    # 按条件读取最近的记录。
    async def recent(self, rules: RunFilter, limit: int) -> list[RunRecord]:
        columns = run_records.c
        query = select(columns.body).order_by(columns.started_at.desc()).limit(limit)
        for column, value in [
            (columns.module, rules.module),
            (columns.contract, rules.contract),
            (columns.status, rules.status),
            (columns.request_id, rules.request_id),
            (columns.job_id, rules.job_id),
        ]:
            if value:
                query = query.where(column == value)
        if rules.before is not None:
            query = query.where(columns.started_at < rules.before)
        if rules.top_only:
            query = query.where(columns.parent_id == "")
        async with self.database.read() as connection:
            bodies = (await connection.scalars(query)).all()
        return [run_from_dict(json.loads(body)) for body in bodies]

    # 删除早于指定时间的记录。
    async def clean(self, older_than: float) -> int:
        query = delete(run_records).where(run_records.c.started_at < older_than)
        async with self.database.write() as connection:
            result = await connection.execute(query)
        return int(result.rowcount or 0)


# 把运行记录转成数据库行；步骤详情整体保存为 JSON。
def to_row(run: RunRecord) -> dict[str, object]:
    return {
        "id": run.id,
        "root_id": run.root_id,
        "parent_id": run.parent_id,
        "contract": run.contract,
        "module": run.module,
        "status": run.status,
        "request_id": run.request_id,
        "job_id": run.job_id,
        "started_at": run.started_at,
        "elapsed_ms": run.elapsed_ms,
        "summary": run.summary,
        "body": json.dumps(run.to_dict(), ensure_ascii=False),
    }
