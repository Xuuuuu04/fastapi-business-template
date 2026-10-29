from fastapi.testclient import TestClient

from tests.failure_reports import FINISHED, failure_reports
from tests.framework.sample_modules import count_total
from tests.testing_app import KEY


def test_reports_only_failed_runs(sample_client: TestClient) -> None:
    sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY)
    assert failure_reports(FINISHED) == []
    sample_client.post("/test/calc", json={"amount": "5", "fail_at": "total"}, headers=KEY)
    reports = failure_reports(FINISHED)
    assert len(reports) == 1
    title, text = reports[0]
    assert title.startswith("运行报告 ")
    assert "在“计算应付”步骤停止：ValueError" in text
    assert f"{count_total.source} · {count_total.name}" in text
    assert "故意在计算时失败" not in text
