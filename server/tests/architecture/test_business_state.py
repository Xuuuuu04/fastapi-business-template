import json
import os
import time
from pathlib import Path

import pytest
from fastapi_project.development.business_runtime import observe
from fastapi_project.development.business_state import (
    END,
    FOLDER,
    MAX_AGE,
    database_identity,
    outdated,
    read,
    update,
)
from sqlalchemy import select
from sqlalchemy import update as change

from app.setup.build import build
from app.setup.drill import prepare, settings_for
from shared.access.caller import SYSTEM
from shared.drills.isolation import isolated
from shared.jobs.schedule import Scheduler
from shared.jobs.tables import jobs
from shared.modules.catalog import Catalog
from shared.pipelines.tables import runs
from tests.framework.drill_sample import module as drill_module
from tests.framework.operations_sample import Input, critical, module


def project(root: Path) -> None:
    folder = root / "server/service/ops_sample"
    folder.mkdir(parents=True)
    (folder / "module.py").write_text("# 独立测试源码\n")


def test_generated_state_preserves_manual_and_detects_expiry(tmp_path: Path) -> None:
    project(tmp_path)
    catalog = Catalog([module])
    [path] = update(catalog, tmp_path, set())
    manual = (
        "\n## 手写部分\n\n业务判断：测试约定已确认。\n"
        "外部依赖：录制平台。\n下一步：真实规模演练。\n"
    )
    path.write_text(path.read_text().split(END)[0] + END + manual)
    update(catalog, tmp_path, set())
    assert path.read_text().endswith(manual)
    assert "未知（还没有连接数据库读取过）" in path.read_text()
    assert outdated(catalog, tmp_path, set()) == []
    data = read(path)
    assert data and outdated(catalog, tmp_path, set(), now=data["generated_at"] + MAX_AGE + 1) == []
    assert outdated(catalog, tmp_path, {module.name}) == [path]
    (tmp_path / "server/service/ops_sample/module.py").write_text("# 已修改计算\n")
    assert outdated(catalog, tmp_path, set()) == [path]
    update(catalog, tmp_path, set())
    path.write_text(path.read_text().replace("**最近运行**：", "**虚构运行**："))
    assert outdated(catalog, tmp_path, set()) == [path]
    update(catalog, tmp_path, set())
    assert path.read_text().endswith(manual) and outdated(catalog, tmp_path, set()) == []


def test_broken_markers_do_not_erase_manual(tmp_path: Path) -> None:
    project(tmp_path)
    path = tmp_path / FOLDER / "ops_sample.md"
    path.parent.mkdir(parents=True)
    path.write_text("# 人工业务判断：不能丢失\n")
    assert outdated(Catalog([module]), tmp_path, set()) == [path]
    with pytest.raises(ValueError, match="边界损坏"):
        update(Catalog([module]), tmp_path, set())
    assert path.read_text() == "# 人工业务判断：不能丢失\n"


def test_bounded_preview_keeps_complete_json(tmp_path: Path) -> None:
    catalog = Catalog([module])
    facts = {
        module.name: dict(
            last="未知",
            overdue="未知",
            observed_at=time.time(),
            confirmation=dict(
                count=50, examples=[{"id": str(index)} for index in range(10)], omitted=40
            ),
        )
    }
    [path] = update(catalog, tmp_path, set(), facts)
    assert "有 50 条" in path.read_text()
    detail = path.with_suffix(".json").read_text()
    assert '"count": 50' in detail and '"omitted": 40' in detail
    data = json.loads(path.with_suffix(".json").read_text())
    assert len(data["runtime"]["confirmation"]["examples"]) == 10
    assert outdated(catalog, tmp_path, set()) == []


def test_database_target_change_expires_observation(tmp_path: Path) -> None:
    catalog = Catalog([module])
    source = (
        "postgresql+psycopg://reader:secret@isolated.invalid/source?options=-csearch_path%3Dalpha"
    )
    identity = database_identity(source)
    facts = {
        module.name: dict(
            last="未知",
            overdue="未知",
            confirmation="未知",
            observed_at=time.time(),
            database_id=identity,
        )
    }
    [path] = update(catalog, tmp_path, set(), facts)
    assert outdated(catalog, tmp_path, set(), database_id=identity) == []
    assert outdated(
        catalog, tmp_path, set(), database_id=database_identity(source.replace("source?", "other?"))
    ) == [path]
    assert database_identity(source.replace("secret", "rotated")) == identity
    assert "isolated.invalid" not in path.with_suffix(".json").read_text()
    assert "secret" not in path.read_text()


@pytest.mark.anyio
async def test_real_database_observation_is_read_only(tmp_path: Path) -> None:
    postgres = os.environ.get("APP_TEST_DATABASE_URL", "")
    async with isolated(tmp_path, postgres if postgres.startswith("postgresql") else "") as url:
        settings = settings_for(url, tmp_path, {"recorded_upstream"})
        settings.run_records = "database"
        built = build(settings, modules=[module, drill_module])
        try:
            await prepare(built)
            await built.runtime.run(critical, Input(), caller=SYSTEM)
            await built.recorder.flush()
            await Scheduler(built.catalog.schedules, built.queue, built.database).tick(time.time())
            async with built.database.write() as conn:
                pending = await built.queue.submit(
                    conn, critical, Input(), SYSTEM, key="confirm", request_id=""
                )
                await conn.execute(change(jobs).where(jobs.c.id == pending).values(state="unknown"))
                await conn.execute(change(runs).values(overdue=True, complete_by=time.time() - 10))
            facts = await observe(built.database, built.catalog)
            assert facts[module.name]["last"]["operation"]["status"] == "ok"
            assert facts[module.name]["confirmation"]["count"] == 1
            assert facts[drill_module.name]["overdue"]["count"] == 1
            assert (
                facts[drill_module.name]["last"]["pipelines"]["drill_sample.daily"]["state"]
                == "running"
            )
            [path] = update(built.catalog, tmp_path, set(), facts, names=[module.name])
            assert "不证明当前源码成功" in path.read_text()
            async with built.database.read() as conn:
                assert (
                    await conn.scalar(select(jobs.c.state).where(jobs.c.id == pending)) == "unknown"
                )
            assert outdated(built.catalog, tmp_path, set()) == [
                tmp_path / FOLDER / "drill_sample.md"
            ]
        finally:
            await built.close()
