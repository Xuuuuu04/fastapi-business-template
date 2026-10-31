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


def test_http_run_identifies_sql_and_outputs(sample_client: TestClient) -> None:
    client = sample_client
    response = client.post("/test/calc", json={"amount": "5"}, headers=KEY)
    assert response.status_code == 200 and response.json()["saved"] == 1
    run_id = response.headers["x-run-id"]
    detail = client.get(f"/api/system/runs/{run_id}", headers=KEY).json()
    run = detail["runs"][0]
    assert run["status"] == "ok"
    recorded = next(part for part in run["steps"] if part["database_count"])
    assert recorded["outputs"]
    assert recorded["elapsed_ms"] > 0 and recorded["database_count"] == 2
    assert [call["method"] for call in recorded["database"]] == ["change", "scalar"]
    for call in recorded["database"]:
        assert call["source"].startswith("tests/framework/sample_modules.py:")
        assert call["function"] == "save_total" and call["elapsed_ms"] > 0
        assert call["tables"] == ["sample_calc_notes"] and call["status"] == "ok"
    assert recorded["database"][0]["rows"] == 1
    graph = detail["graph"]
    assert recorded["source"] in graph and recorded["name"] in graph
    assert "sample_modules.py:" in graph and "save_total" in graph
    report = client.get(f"/api/system/runs/{run_id}/report", headers=KEY).text
    assert "耗时最长的步骤" in report and "数据库调用" in report and "sample_calc_notes" in report


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
    assert "已写入 1/1 个声明字段" in run_graph([run]) and "数据库调用" in run_report([run], run.id)


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


@pytest.mark.anyio
async def test_development_evidence_omits_business_values(sample: Services) -> None:
    await sample.runtime.run(calc, CalcInput(amount=Decimal("987654321.123")), caller=DEVELOPER)
    run = (await sample.recorder.recent(RunFilter(), 1))[0]
    evidence = run_evidence(run)
    assert "987654321" not in str(evidence) and "key:" not in str(evidence)
    assert any(step["outputs"].get("total") == "已写入数字" for step in evidence["steps"])
    assert run_from_dict(run.to_dict()) == run
    with pytest.raises(TypeError):
        run_from_dict({**run.to_dict(), "source_version": "removed-field"})
    without_steps = run.to_dict()
    del without_steps["steps"][0]["database"]
    with pytest.raises(KeyError):
        run_from_dict(without_steps)
