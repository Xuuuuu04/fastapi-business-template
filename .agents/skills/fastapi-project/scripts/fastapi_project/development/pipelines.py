import json
import time
from pathlib import Path
from typing import Any

from shared.db.database import Database
from shared.modules.catalog import Catalog
from shared.pipelines.plan import FanOut
from shared.pipelines.views import list_runs

CACHE = "server/var/development/pipeline-state.json"


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
