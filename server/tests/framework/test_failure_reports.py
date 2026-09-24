"""
验证测试失败时附上的运行报告：只取失败的最外层运行，报告写明失败步骤和原因。
"""

from fastapi.testclient import TestClient

from tests.failure_reports import FINISHED, failure_reports
from tests.testing_app import KEY


# 成功的运行不出报告；失败的运行给出包含失败步骤和错误说明的中文报告。
def test_reports_only_failed_runs(sample_client: TestClient) -> None:
    sample_client.post("/test/calc", json={"amount": "5"}, headers=KEY)
    assert failure_reports(FINISHED) == []
    sample_client.post("/test/calc", json={"amount": "5", "fail_at": "total"}, headers=KEY)
    reports = failure_reports(FINISHED)
    assert len(reports) == 1
    title, text = reports[0]
    assert title.startswith("运行报告 ")
    assert "计算应付" in text and "故意在计算时失败" in text
