"""
流程声明及运行摘要：默认只读本机缓存，明确未知；--runs才查询数据库并刷新缓存。
"""

import json
import time
from pathlib import Path
from typing import Any

from shared.db.database import Database
from shared.modules.catalog import Catalog
from shared.pipelines.plan import FanOut
from shared.pipelines.views import list_runs

CACHE = "server/var/development/pipeline-state.json"


# 所有流程均列声明，最近运行没有证据时标未知，不把登记当作执行完成。
def overview(catalog: Catalog, project: Path, *, module: str = "") -> list[dict[str, Any]]:
    path = project / CACHE
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    result = []
    for pipeline in catalog.pipelines.values():
        if module and pipeline.name.partition(".")[0] != module:
            continue
        item = dict(
            name=pipeline.name,
            title=pipeline.title,
            overlap=pipeline.overlap,
            on_overdue=pipeline.on_overdue,
            stage_count=len(pipeline.stages),
            last=saved.get("runs", {}).get(pipeline.name),
            observed_at=saved.get("observed_at"),
            evidence="本机运行摘要缓存" if saved else "未知：尚未读取数据库",
        )
        result.append(item)
    return result


# 逐个流程只保留最新一条有界摘要，刷新动作不会修改业务库。
async def refresh(database: Database, catalog: Catalog, project: Path) -> None:
    found = await list_runs(database, limit=1000)
    latest: dict[str, dict[str, Any]] = {}
    for row in found:
        latest.setdefault(row["pipeline"], row)
    path = project / CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(observed_at=time.time(), runs=latest), ensure_ascii=False, indent=2)
    )


# 一个操作属于哪些流程和阶段，扇出子阶段也提供完整定位。
def memberships(catalog: Catalog, operation: str) -> list[dict[str, str]]:
    result = []
    for pipeline in catalog.pipelines.values():
        if operation == pipeline.start.name:
            result.append(dict(pipeline=pipeline.name, stage="启动入口"))
        for stage in pipeline.stages:
            if stage.operation.name == operation:
                result.append(dict(pipeline=pipeline.name, stage=stage.name))
            children = stage.stages if isinstance(stage, FanOut) else ()
            result += [
                dict(pipeline=pipeline.name, stage=stage.name + "/" + child.name)
                for child in children
                if child.operation.name == operation
            ]
    return result
