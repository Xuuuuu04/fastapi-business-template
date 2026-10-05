"""
读取可选的数据库运行记录，只提供开发状态所需的名称、版本和结束状态。
这些记录可能来自旧版本；不能用它们声称当前代码已通过测试。
"""

from typing import Any

from shared.config.settings import Settings
from shared.db.database import Database
from shared.graphs.observed import run_graph
from shared.records.evidence import run_evidence
from shared.records.stores import RunFilter, SqlRunStore
from shared.records.version import source_version
from tools.quality.rules import ROOT


# 仅在用户明确请求运行记录时访问当前配置的数据库。
async def recent_runs(settings: Settings, limit: int, module: str = "") -> dict[str, Any]:
    if settings.run_records != "database":
        return {
            "available": False,
            "reason": "运行记录保存在服务进程内存中，请使用系统接口",
            "runs": [],
            "successful": [],
            "current_successful": [],
        }
    database = Database(settings.database_url)
    try:
        store = SqlRunStore(database)
        records = await store.recent(RunFilter(module=module, top_only=False), limit)
        runs = [{**run_evidence(run), "graph": run_graph([run])} for run in records]
        successful = sorted(
            {run.contract for run in records if run.status == "ok" and not run.gaps}
        )
        version = source_version(ROOT)
        current = sorted(
            {
                run.contract
                for run in records
                if run.status == "ok" and not run.gaps and run.source_version == version
            }
        )
        return {
            "available": True,
            "limit": limit,
            "runs": runs,
            "successful": successful,
            "current_successful": current,
            "source_version": version,
            "graph": run_graph(records),
        }
    finally:
        await database.close()
