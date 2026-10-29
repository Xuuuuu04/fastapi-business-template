from pathlib import Path

import pytest
from fastapi_project.development.pipelines import memberships, overview, refresh

from shared.modules.catalog import Catalog
from tests.framework.fanout_sample import collect
from tests.framework.fanout_sample import module as fanout_module
from tests.framework.pipeline_sample import module
from tests.framework.test_pipelines import drain, piped, start

__all__ = ["piped"]


def test_pipeline_summary_unknown_and_operation_membership(tmp_path: Path) -> None:
    catalog = Catalog([module, fanout_module])
    info = overview(catalog, tmp_path)
    assert len(info) == 2 and all(item["last"] is None for item in info)
    assert all("未知" in item["evidence"] for item in info)
    assert memberships(catalog, collect.name) == [
        {"pipeline": "fanout_sample.daily", "stage": "requests/submit"}
    ]


@pytest.mark.anyio
async def test_pipeline_snapshot_from_real_run(piped, tmp_path: Path) -> None:
    run_id = await start(piped, "summary")
    await drain(piped)
    await refresh(piped.database, piped.catalog, tmp_path)
    info = overview(piped.catalog, tmp_path)
    assert info[0]["last"]["id"] == run_id
    assert info[0]["last"]["state"] == "succeeded" and info[0]["last"]["current_stage"] == "publish"
    assert info[0]["observed_at"] > 0 and "缓存" in info[0]["evidence"]
