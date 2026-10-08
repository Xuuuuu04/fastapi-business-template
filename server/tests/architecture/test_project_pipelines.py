"""
项目摘要默认不读业务库；流程缓存明确证据时间和未知，操作详情定位到扇出子阶段。
"""

from pathlib import Path

import pytest
from fastapi_project.development.pipelines import memberships, overview, refresh

from shared.modules.catalog import Catalog
from tests.framework.fanout_sample import collect
from tests.framework.fanout_sample import module as fanout_module
from tests.framework.pipeline_sample import module
from tests.framework.test_pipelines import drain, piped, start

__all__ = ["piped"]


# 未刷新数据库之前只显示未知，不从声明猜业务运行状态。
def test_pipeline_summary_unknown_and_operation_membership(tmp_path: Path) -> None:
    catalog = Catalog([module, fanout_module])
    info = overview(catalog, tmp_path)
    assert len(info) == 2 and all(item["last"] is None for item in info)
    assert all("未知" in item["evidence"] for item in info)
    assert memberships(catalog, collect.name) == [
        {"pipeline": "fanout_sample.daily", "stage": "requests/submit"}
    ]


# --runs使用的刷新动作读取实际结果，后续默认摘要使用同一缓存并标观察时间。
@pytest.mark.anyio
async def test_pipeline_snapshot_from_real_run(piped, tmp_path: Path) -> None:
    run_id = await start(piped, "summary")
    await drain(piped)
    await refresh(piped.database, piped.catalog, tmp_path)
    info = overview(piped.catalog, tmp_path)
    assert info[0]["last"]["id"] == run_id
    assert info[0]["last"]["state"] == "succeeded" and info[0]["last"]["current_stage"] == "publish"
    assert info[0]["observed_at"] > 0 and "缓存" in info[0]["evidence"]
