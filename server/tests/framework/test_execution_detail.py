"""
实际运行细节：通过 HTTP 验证步骤产出、SQL 耗时和存储函数位置；失败保留部分产出。
旧记录保持可读且标明未知；开发历史不包含显式允许记录的业务取值。
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.setup.build import Services
from shared.access.caller import DEVELOPER
from shared.graphs.observed import run_graph, run_report
from shared.records.evidence import run_evidence
from shared.records.models import run_from_dict
from shared.records.stores import RunFilter
from tests.framework.sample_modules import CalcInput, SlowInput, calc, slow
from tests.testing_app import KEY


# 查询文件列表产生两次真实 SQL，图和报告都能指出存储函数与字段产出。
def test_http_run_identifies_sql_and_outputs(client: TestClient) -> None:
    response = client.get("/api/v1/files/detail-test", headers=KEY)
    assert response.status_code == 200 and response.json()["items"] == []
    run_id = client.get("/api/system/runs?module=file_library", headers=KEY).json()["items"][0][
        "id"
    ]
    detail = client.get(f"/api/system/runs/{run_id}", headers=KEY).json()
    run = detail["runs"][0]
    assert run["source_version"] and run["status"] == "ok"
    step = next(step for step in run["steps"] if step["database_count"])
    assert step["outputs_recorded"] and step["outputs"]
    assert step["elapsed_ms"] > 0 and step["database_count"] == 2
    assert [call["method"] for call in step["database"]] == ["scalar", "all"]
    for call in step["database"]:
        assert call["source"].startswith("service/file_library/store/sql.py:")
        assert call["function"] == "list_files" and call["elapsed_ms"] > 0
        assert call["tables"] == ["file_library_files"] and call["status"] == "ok"
    assert step["database"][0]["rows"] is None and step["database"][1]["rows"] == 0
    graph = detail["graph"]
    assert step["source"] in graph and step["name"] in graph and "产出 1/1" in graph
    assert "file_library/store/sql.py:" in graph and "list_files" in graph
    report = client.get(f"/api/system/runs/{run_id}/report", headers=KEY).text
    assert "最长步骤" in report and "数据库调用" in report and "file_library_files" in report


# 条件判断有自己的函数位置和耗时；跳过仍然没有产出。
@pytest.mark.anyio
async def test_condition_and_partial_failure(sample: Services) -> None:
    await sample.runtime.run(calc, CalcInput(amount=Decimal("5")), caller=DEVELOPER)
    skipped = (await sample.recorder.recent(RunFilter(), 1))[0].steps[0]
    assert skipped.status == "skipped" and skipped.condition_result is False
    assert skipped.condition_source and skipped.condition_name and skipped.condition_elapsed_ms > 0
    assert skipped.outputs == {}
    with pytest.raises(ValueError):
        await sample.runtime.run(
            calc, CalcInput(amount=Decimal("5"), fail_at="save"), caller=DEVELOPER
        )
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    failed = next(step for step in run.steps if step.status == "failed")
    assert failed.outputs == {"saved": "已写入数字"}
    assert failed.database_count == 2 and failed.elapsed_ms > 0
    assert "产出 1/1" in run_graph([run]) and "数据库调用" in run_report([run], run.id)


# 一个耗时步骤会在真实记录中比保存步骤更慢，并出现在报告的最长步骤处。
@pytest.mark.anyio
async def test_measured_slow_step_is_visible(sample: Services) -> None:
    result = await sample.runtime.run(
        slow, SlowInput(seconds=0.05, mark="latency-test"), caller=DEVELOPER
    )
    assert result.saved == 1
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    longest = max(run.steps, key=lambda step: step.elapsed_ms)
    assert longest.name == "wait_some" and longest.elapsed_ms >= 40
    assert longest.source in run_graph([run])
    assert f"{longest.source} · wait_some" in run_report([run], run.id)


# 开发历史只给字段形状；金额 log_value 允许写入普通运行报告，也不会进入开发记录。
@pytest.mark.anyio
async def test_development_evidence_omits_business_values(sample: Services) -> None:
    await sample.runtime.run(calc, CalcInput(amount=Decimal("987654321.123")), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    evidence = run_evidence(run)
    assert "987654321" not in str(evidence) and "key:" not in str(evidence)
    assert any(step["outputs"].get("total") == "已写入数字" for step in evidence["steps"])
    assert run_from_dict(run.to_dict()) == run
    legacy = run.to_dict()
    legacy.pop("source_version")
    for step in legacy["steps"]:
        for field in (
            "outputs",
            "outputs_recorded",
            "database",
            "database_count",
            "database_elapsed_ms",
            "database_complete",
        ):
            step.pop(field)
    old = run_from_dict(legacy)
    assert old.source_version == "" and "产出未知（旧记录）" in run_graph([old])
