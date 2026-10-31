import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, func, insert, select

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

    async def save(self, runs: list[RunRecord]) -> None: ...

    async def get(self, run_id: str) -> RunRecord | None: ...

    async def tree(self, root_id: str) -> list[RunRecord]: ...

    async def recent(self, rules: RunFilter, limit: int) -> list[RunRecord]: ...

    async def clean(self, older_than: float) -> int: ...

    async def stats(self, since: float, module: str = "") -> list[dict[str, object]]: ...


class MemoryRunStore:
    immediate = True

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.rows: OrderedDict[str, RunRecord] = OrderedDict()
        self.dropped = 0

    async def save(self, runs: list[RunRecord]) -> None:
        for run in runs:
            self.rows[run.id] = run
        while len(self.rows) > self.limit:
            self.rows.popitem(last=False)
            self.dropped += 1

    async def get(self, run_id: str) -> RunRecord | None:
        return self.rows.get(run_id)

    async def tree(self, root_id: str) -> list[RunRecord]:
        return [run for run in self.rows.values() if run.root_id == root_id]

    async def recent(self, rules: RunFilter, limit: int) -> list[RunRecord]:
        found = [run for run in reversed(self.rows.values()) if matches(run, rules)]
        return sorted(found, key=lambda run: (run.started_at, run.id), reverse=True)[:limit]

    async def clean(self, older_than: float) -> int:
        old = [key for key, run in self.rows.items() if run.started_at < older_than]
        for key in old:
            del self.rows[key]
        return len(old)

    async def stats(self, since: float, module: str = "") -> list[dict[str, object]]:
        selected = [
            run
            for run in self.rows.values()
            if run.started_at >= since
            and not run.parent_id
            and run.status not in ("running", "lost")
            and (not module or run.module == module)
        ]
        groups: dict[tuple[str, str], list[float]] = {}
        for run in selected:
            groups.setdefault((run.contract, run.status), []).append(run.elapsed_ms)
        return [
            {
                "contract": name,
                "status": status,
                "count": len(times),
                "average_ms": round(sum(times) / len(times), 1),
                "max_ms": round(max(times), 1),
            }
            for (name, status), times in sorted(groups.items())
        ]


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

    def __init__(self, database: Database) -> None:
        self.database = database
        self.dropped = 0

    async def save(self, runs: list[RunRecord]) -> None:
        if not runs:
            return
        rows = [to_row(run) for run in runs]
        async with self.database.write() as connection:
            await connection.execute(
                delete(run_records).where(run_records.c.id.in_([run.id for run in runs]))
            )
            await connection.execute(insert(run_records), rows)

    async def get(self, run_id: str) -> RunRecord | None:
        query = select(run_records.c.body).where(run_records.c.id == run_id)
        async with self.database.read() as connection:
            body = await connection.scalar(query)
        return None if body is None else run_from_dict(json.loads(body))

    async def tree(self, root_id: str) -> list[RunRecord]:
        query = select(run_records.c.body).where(run_records.c.root_id == root_id)
        async with self.database.read() as connection:
            bodies = (await connection.scalars(query.order_by(run_records.c.started_at))).all()
        return [run_from_dict(json.loads(body)) for body in bodies]

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

    async def clean(self, older_than: float) -> int:
        query = delete(run_records).where(run_records.c.started_at < older_than)
        async with self.database.write() as connection:
            result = await connection.execute(query)
        return int(result.rowcount or 0)

    async def stats(self, since: float, module: str = "") -> list[dict[str, object]]:
        query = (
            select(
                run_records.c.contract,
                run_records.c.status,
                func.count().label("count"),
                func.avg(run_records.c.elapsed_ms).label("average_ms"),
                func.max(run_records.c.elapsed_ms).label("max_ms"),
            )
            .where(
                run_records.c.started_at >= since,
                run_records.c.parent_id == "",
                run_records.c.status.not_in(("running", "lost")),
            )
            .group_by(run_records.c.contract, run_records.c.status)
            .order_by(run_records.c.contract, run_records.c.status)
        )
        if module:
            query = query.where(run_records.c.module == module)
        async with self.database.read() as connection:
            rows = (await connection.execute(query)).mappings().all()
        return [
            {
                "contract": row["contract"],
                "status": row["status"],
                "count": row["count"],
                "average_ms": round(row["average_ms"], 1),
                "max_ms": round(row["max_ms"], 1),
            }
            for row in rows
        ]


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
